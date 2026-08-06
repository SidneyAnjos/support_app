import os 
import uuid
import pandas as pd
import psycopg2
from psycopg2 import sql
import streamlit as st

#first we need to configure the page
st.set_page_config(
    page_title= "AI Support Portal - Lakebase", page_icon= "🎫", layout="wide"
)

#Connect to lakebase postgres
def get_db_connection():
    """Connect to lakebase postgres database and return the connection object or Streamlit Secrets."""
    return psycopg2.connect(
        host=os.getenv(
            "LAKEBASE_HOST", st.secrets.get("LAKEBASE_HOST", "localhost")
        ),
        port=int(
            os.getenv("LAKEBASE_PORT", st.secrets.get("LAKEBASE_PORT", "5432"))
        ),
        dbname=os.getenv(
            "LAKEBASE_DB", st.secrets.get("LAKEBASE_DB", "databricks_postgres")
        ),
        password=os.getenv(
            "LAKEBASE_PASSWORD", st.secrets.get("LAKEBASE_PASSWORD", "")
        ),
        #make sure to use the correct username for your schema is the same as one in DB
        options="-c search_path=support_app, public",   
    )
def execute_dml(query, prams=None):
    """Execute a query and return a Pandas Dataframe"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, prams)
            res = cur.fetchall()
            return pd.DataFrame(res) if res else pd.DataFrame()
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
                "SELECT * FROM support_app.ticket_messages WHERE ticket_id = %s ORDER BY created_at ASC:",
                (selected_ticket_id,)
            )

            if not df_msgs.empty:
                for _, msg in df_msgs.iterrows():
                    with st.chat_messages(msg["author"]):
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
        title = st.text_input("Ticket Title")
        created_by = st.text_input("Your Name or E-mail")

        #new category inserted
        category = st.selectbox(
            "Category", [
            "Technical Support",
            "Billing & Payments",
            "Account Management",
            "Feature Requests",
            "General",],
        )
    #New Priority inserted
    priority = st.selectbox(
        "Priority", [
            "Low", 
            "Medium", 
            "High", 
            "Critical"]
    )    
    initial_message = st.text_area("Description of the issue or request")

    submitted = st.form_submit_button("Create Ticket")

    if submitted:
        if not title or not created_by or not created_by or not initial_message:
            st.error(
                "Please fill in all fields required fields marked with (*)"
            )
        else:
            new_ticket_id = f"tkt_{uuid.uuid4().hex[:6]}"
            new_msg_id = f"msg_{uuid.uuid4().hex[:6]}"

            try:
                #insert ticket
                execute_dml(
                    "INSERT INTO support_app.tickets (ticket_id, title, created_by, status, priority, category) VALUES (%s, %s, 'open', %s, %s, %s);"
                    (new_ticket_id, title, priority, category, created_by),
                )
                #insert initial message
                execute_dml(
                    "INSERT INTO support_app.ticket_messages (message_id, ticket_id, message_text, author) VALUES (%s, %s, %s, %s);",
                    (new_msg_id, new_ticket_id, initial_message, created_by),
                )
                st.success(
                    f"Ticket **{new_ticket_id}** successfully created in lakebase!"
                )
            except Exception as e:
                st.error(f"Error saving ticket in database: {e}")
# ==============================================================================
#Option 3

elif menu_option == "📊 Statistics":
    st.header("📊 General Ticket Menu")

    df_all = run_query("SELECT * FROM support_app.tickets:")

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
    #Spliting the distribuition graphs into two columns
    chat_col1, chat_col2 = st.columns(2)

    with chart_col1:
        st.subheader("By Category")
        st.bar_chart(df_all["category"].value_counts())
    with chart_col2:
        st.subheader("By Priority")
        st.bar_chart(df_all["priority"].value_counts())