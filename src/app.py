import os
import uuid
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from abc import ABC, abstractmethod
import streamlit as st
from databricks.sdk.core import Config

class BaseTextInput(ABC):
    @abstractmethod
    def render(self):
        """Render the text input widget."""
        pass

    @abstractmethod
    def get_value(self):
        """Return the current widget value."""
        pass

    @abstractmethod
    def set_value(self, value):
        """Update the current widget value."""
        pass

class text_input(BaseTextInput):
    def __init__(
        self,
        label,
        value="",
        max_chars=None,
        key=None,
        type="default",
        help=None,
        placeholder=None,
        disabled=False,
        label_visibility="visible",
    ):
        self.label = label
        self.value = value
        self.max_chars = max_chars
        self.key = key
        self.type = type
        self.help = help
        self.placeholder = placeholder
        self.disabled = disabled
        self.label_visibility = label_visibility
        self._current_value = value

    def render(self):
        self._current_value = st.text_input(
            self.label,
            value=self._current_value,
            max_chars=self.max_chars,
            key=self.key,
            type=self.type,
            help=self.help,
            placeholder=self.placeholder,
            disabled=self.disabled,
            label_visibility=self.label_visibility,
        )
        return self._current_value

    def get_value(self):
        return self._current_value

    def set_value(self, value):
        self._current_value = value

#first we need to configure the page
st.set_page_config(
    page_title= "AI Support Portal - Lakebase", page_icon= "🎫", layout="wide"
)

#Connect to lakebase postgres
def get_config(key, default_val):
    """SEARCHING FOR CONFIGURATION VALUES IN ENVIRONMENT VARIABLES OR STREAMLIT SECRETS."""
    env_val = os.getenv(key)
    if env_val is not None:
        return env_val
        
    try:
        return st.secrets.get(key, default_val)
    except FileNotFoundError:
        return default_val

def get_db_connection():
    """Connect to Lakebase using OAuth token from the app's service principal."""
    cfg = Config()
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "databricks_postgres"),
        user=os.environ["PGUSER"],
        password=cfg.oauth_token().access_token,
        sslmode="require",
        options="-c search_path=support_app,public",
    )
def run_query(query, params=None):
    """Execute SELECT queries and return results as a pandas DataFrame."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            res = cur.fetchall()
            return pd.DataFrame(res) if res else pd.DataFrame()

def execute_dml(query, params=None):
    """Executes INSERT, UPDATE, DELETE."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
#navigation menu sidebar
st.sidebar.title("🎫 SSupport Portal")
menu_option = st.sidebar.radio(
    "Navegation",
    ["📋 Visualize tickets ", "➕ Create a new Ticket", "📊 Statistics"],
)
st.sidebar.divider()
st.sidebar.info("Connected to Lakebase Postgres Database")

# ==============================================================================
# FIRST OPTION INTERACTING WITH TICKETS
if menu_option == "📋 Visualize tickets ":
    st.header("📋 Manage tickets")

#filter by status
    status_filter = st.selectbox(
        "Filter by status:", ["All", "Open", "In Progress", "Resolved"]
    )
#query dinamyc Ps:attention for the schema name
    if status_filter == "All":
        df_tickets = run_query(
            "SELECT * FROM support_app.tickets ORDER BY created_at DESC"
        )
    else:
        df_tickets = run_query(
            "SELECT * FROM support_app.tickets WHERE status = %s ORDER BY created_at DESC",
            (status_filter,)
        )
    if df_tickets.empty:
        st.warning("No tickets found for the selected status.")
    else:
        #Ticket selection
        ticket_options = {
            row["ticket_id"]: (
                f"[{row['ticket_id']}] {row['title']} | Status: {row['status']} |Priority:{row['priority']}"
            )
            for _, row in df_tickets.iterrows()
        }

        selected_ticket_id = st.selectbox(
            "Select a ticket to view details:",
            options=list(ticket_options.keys()),
            format_func=lambda x: ticket_options[x],
        )
        if selected_ticket_id:
            ticket = df_tickets[df_tickets["ticket_id"] == selected_ticket_id].iloc[0]

            st.markdown("---")
            st.subheader(f"Ticket {ticket['title']}")

            #Visual metrics from tickets
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("ID", ticket["ticket_id"])
            col2.metric("Status", ticket["status"])
            col3.metric("Ticket Priority", ticket["priority"])
            col4.metric("Ticket Category", ticket["category"])

            st.write(f"**Created by: ** {ticket['created_by']}")

            #Status atualization
            with st.expander("⚙️ Change Ticket Status"):
                new_status = st.selectbox(
                    "New Status",
                    ["Open", "In Progress", "Resolved"],
                    index=["Open", "In Progress", "Resolved"].index(ticket["status"]),
                    key= "status_select",
                )
            if st.button("Update Status"):
                execute_dml(
                    "UPDATE support_app.tickets SET status = %s WHERE ticket_id = %s",
                    (new_status, selected_ticket_id),
                )
                st.success(f"Status updated to '{new_status}' sucessfully!")
                st.rerun()
            #Message history
            st.subheader("💬 Message History")
            df_msgs = run_query(
                "SELECT * FROM support_app.ticket_messages WHERE ticket_id = %s ORDER BY created_at ASC",
                (selected_ticket_id,)
            )

            if not df_msgs.empty:
                for _, msg in df_msgs.iterrows():
                    with st.chat_message(msg["author"]):
                        st.write(f"**{msg['author']}** - *{msg['created_at']}*")
                        st.write(msg["message_text"])
            else:
                st.info("No new messages for this ticket.")

            #---Add new messages ---
            st.markdown("#### Send message")
            with st.form(key= "add_message_from", clear_on_submit=True):
                author_input = st.text_input("Your Name or e-mail")
                message_input = st.text_area("Your Message here")
                submit_msg = st.form_submit_button("Send Message")

                if submit_msg:
                    if not author_input or not message_input:
                        st.error("Please fill in both fields before sending the message.")
                    else:
                        new_msg_id = f"msg_{uuid.uuid4().hex[:6]}"
                        execute_dml(
                            "INSERT INTO support_app.ticket_messages (message_id, ticket_id, message_text, author) VALUES (%S, %S, %S, %S);",
                            (new_msg_id, selected_ticket_id, message_input, author_input),
                        )
                        st.success("Message sent successfully!")
                        st.rerun()
# ==============================================================================
#Option 2 : CERATE NEW TICKET

elif menu_option == "➕ Create a new Ticket":
    st.header("➕ Create a new Ticket")

    with st.form("create_ticket_form", clear_on_submit=True):
        title_input = text_input("Ticket Title", key="ticket_title")
        title = title_input.render()
        created_by_input = text_input("Your Name or e-mail", key="ticket_created_by")
        created_by = created_by_input.render()

        category = st.selectbox(
            "Category", [
                "Technical Support",
                "Billing & Payments",
                "Account Management",
                "Feature Requests",
                "General",
            ],
        )

        priority = st.selectbox(
            "Priority", [
                "Low",
                "Medium",
                "High",
                "Critical",
            ]
        )

        initial_message = st.text_area("Description of the issue or request")

        submitted = st.form_submit_button("Create Ticket")

        if submitted:
            if not title or not created_by or not initial_message:
                st.error("Please fill in all fields required fields marked with (*)")
            else:
                new_ticket_id = f"tkt_{uuid.uuid4().hex[:6]}"
                new_msg_id = f"msg_{uuid.uuid4().hex[:6]}"

                try:
                    execute_dml(
                        "INSERT INTO support_app.tickets (ticket_id, title, created_by, status, priority, category) VALUES (%s, %s, %s, 'Open', %s, %s);",
                        (new_ticket_id, title, created_by, priority, category),
                    )
                    execute_dml(
                        "INSERT INTO support_app.ticket_messages (message_id, ticket_id, message_text, author) VALUES (%s, %s, %s, %s);",
                        (new_msg_id, new_ticket_id, initial_message, created_by),
                    )
                    st.success(f"Ticket **{new_ticket_id}** successfully created in lakebase!")
                except Exception as e:
                    st.error(f"Error saving ticket in database: {e}")
# ==============================================================================
#Option 3
elif menu_option == "📊 Statistics":
    st.header("📊 General Ticket Menu")

    df_all = run_query("SELECT * FROM support_app.tickets")

    if df_all.empty:
        st.info("No tickets found in the database.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total tickets", len(df_all))
        col2.metric(
            "Open tickets", len(df_all[df_all["status"] == "Open"]), delta_color="normal"
        )
        col3.metric(
            "In Progress tickets", len(df_all[df_all["status"] == "In Progress"]),
        )
        col4.metric("Resolved tickets", len(df_all[df_all["status"] == "Resolved"]))

        st.markdown("---")

        # Splitting the distribution graphs into two columns
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.subheader("By Category")
            st.bar_chart(df_all["category"].value_counts())
        with chart_col2:
            st.subheader("By Priority")
            st.bar_chart(df_all["priority"].value_counts())