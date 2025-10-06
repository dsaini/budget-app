import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
import plaid

# Page config
st.set_page_config(page_title="Family Budget Tracker", layout="wide")

# Data file paths
TRANSACTIONS_FILE = "transactions.csv"
BUDGETS_FILE = "budgets.json"
CATEGORIES_FILE = "categories.json"
PLAID_FILE = "plaid_tokens.json"

# Default categories
DEFAULT_CATEGORIES = [
    "Groceries", "Dining Out", "Gas/Transportation", "Utilities",
    "Entertainment", "Healthcare", "Shopping", "Housing", "Other"
]

# Plaid Configuration
def init_plaid_client():
    """Initialize Plaid API client"""
    try:
        # Get credentials from Streamlit secrets or environment variables
        client_id = st.secrets.get("PLAID_CLIENT_ID", os.getenv("PLAID_CLIENT_ID"))
        secret = st.secrets.get("PLAID_SECRET", os.getenv("PLAID_SECRET"))
        env = st.secrets.get("PLAID_ENV", os.getenv("PLAID_ENV", "production"))
        
        if not client_id or not secret:
            return None
        
        # Map environment string to Plaid host URL
        # Plaid library uses direct URLs instead of Environment enum
        env_mapping = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com"
        }
        
        host = env_mapping.get(env.lower(), "https://production.plaid.com")
            
        configuration = Configuration(
            host=host,
            api_key={
                'clientId': client_id,
                'secret': secret,
            }
        )
        
        api_client = ApiClient(configuration)
        return plaid_api.PlaidApi(api_client)
    except Exception as e:
        st.error(f"Error initializing Plaid: {str(e)}")
        return None

# Initialize data files
def init_files():
    if not os.path.exists(TRANSACTIONS_FILE):
        pd.DataFrame(columns=["date", "description", "amount", "category", "source", "transaction_id"]).to_csv(TRANSACTIONS_FILE, index=False)
    
    if not os.path.exists(BUDGETS_FILE):
        default_budgets = {cat: 500 for cat in DEFAULT_CATEGORIES}
        with open(BUDGETS_FILE, 'w') as f:
            json.dump(default_budgets, f)
    
    if not os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'w') as f:
            json.dump(DEFAULT_CATEGORIES, f)
    
    if not os.path.exists(PLAID_FILE):
        with open(PLAID_FILE, 'w') as f:
            json.dump({"access_tokens": []}, f)

# Load data
def load_transactions():
    try:
        df = pd.read_csv(TRANSACTIONS_FILE)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
        return df
    except:
        return pd.DataFrame(columns=["date", "description", "amount", "category", "source", "transaction_id"])

def load_budgets():
    try:
        with open(BUDGETS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {cat: 500 for cat in DEFAULT_CATEGORIES}

def load_categories():
    try:
        with open(CATEGORIES_FILE, 'r') as f:
            return json.load(f)
    except:
        return DEFAULT_CATEGORIES

def load_plaid_tokens():
    try:
        with open(PLAID_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"access_tokens": []}

# Save data
def save_transactions(df):
    df.to_csv(TRANSACTIONS_FILE, index=False)

def save_budgets(budgets):
    with open(BUDGETS_FILE, 'w') as f:
        json.dump(budgets, f)

def save_categories(categories):
    with open(CATEGORIES_FILE, 'w') as f:
        json.dump(categories, f)

def save_plaid_tokens(tokens_data):
    with open(PLAID_FILE, 'w') as f:
        json.dump(tokens_data, f)

# Plaid Functions
def create_link_token(client):
    """Create a Plaid Link token"""
    try:
        # Get the app URL for redirect_uri (required by Plaid)
        # For Streamlit Cloud, this will be your app's URL
        redirect_uri = st.secrets.get("REDIRECT_URI", "https://localhost:8501")
        
        request = LinkTokenCreateRequest(
            products=[Products("transactions")],
            client_name="Family Budget Tracker",
            country_codes=[CountryCode('US')],
            language='en',
            user=LinkTokenCreateRequestUser(
                client_user_id='user-' + str(hash(datetime.now()))
            )
        )
        response = client.link_token_create(request)
        return response['link_token']
    except plaid.ApiException as e:
        error_response = json.loads(e.body)
        st.error(f"Plaid API Error: {error_response.get('error_message', str(e))}")
        st.error(f"Error code: {error_response.get('error_code', 'unknown')}")
        return None
    except Exception as e:
        st.error(f"Error creating link token: {str(e)}")
        st.error(f"Error type: {type(e).__name__}")
        return None

def exchange_public_token(client, public_token):
    """Exchange public token for access token"""
    try:
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(request)
        return response['access_token']
    except Exception as e:
        st.error(f"Error exchanging token: {str(e)}")
        return None

def fetch_transactions(client, access_token, start_date, end_date):
    """Fetch transactions from Plaid"""
    try:
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )
        response = client.transactions_get(request)
        transactions = response['transactions']
        
        # Handle pagination if there are more transactions
        while len(transactions) < response['total_transactions']:
            request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=TransactionsGetRequestOptions(
                    offset=len(transactions)
                )
            )
            response = client.transactions_get(request)
            transactions.extend(response['transactions'])
        
        return transactions
    except Exception as e:
        st.error(f"Error fetching transactions: {str(e)}")
        return []

def categorize_transaction(plaid_category):
    """Map Plaid categories to our budget categories"""
    category_mapping = {
        'Food and Drink': 'Dining Out',
        'Groceries': 'Groceries',
        'Transportation': 'Gas/Transportation',
        'Recreation': 'Entertainment',
        'Healthcare': 'Healthcare',
        'Shopping': 'Shopping',
        'Travel': 'Entertainment',
        'Payment': 'Other',
        'Transfer': 'Other',
    }
    
    if plaid_category and len(plaid_category) > 0:
        primary_category = plaid_category[0]
        return category_mapping.get(primary_category, 'Other')
    return 'Other'

def sync_plaid_transactions(client, access_tokens):
    """Sync transactions from all connected accounts"""
    all_new_transactions = []
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=90)  # Last 90 days
    
    existing_df = load_transactions()
    existing_ids = set(existing_df['transaction_id'].dropna().values) if not existing_df.empty else set()
    
    for token_info in access_tokens:
        access_token = token_info['access_token']
        institution_name = token_info.get('institution_name', 'Bank')
        
        transactions = fetch_transactions(client, access_token, start_date, end_date)
        
        for txn in transactions:
            transaction_id = txn['transaction_id']
            
            # Skip if we already have this transaction
            if transaction_id in existing_ids:
                continue
            
            # Only include debit transactions (expenses)
            if txn['amount'] > 0:
                all_new_transactions.append({
                    'date': txn['date'],
                    'description': txn['name'],
                    'amount': abs(txn['amount']),
                    'category': categorize_transaction(txn.get('category')),
                    'source': f'Plaid - {institution_name}',
                    'transaction_id': transaction_id
                })
    
    return all_new_transactions

# Initialize
init_files()
plaid_client = init_plaid_client()

# Sidebar navigation
st.sidebar.title("🏠 Family Budget Tracker")
page = st.sidebar.radio("Navigate", [
    "Dashboard", 
    "Add Expense", 
    "Import CSV", 
    "Sync Banks (Plaid)", 
    "Manage Budget", 
    "History"
])

# Load data
transactions_df = load_transactions()
budgets = load_budgets()
categories = load_categories()
plaid_tokens = load_plaid_tokens()

# Get current month data
def get_month_data(df, year, month):
    if df.empty:
        return pd.DataFrame(columns=["date", "description", "amount", "category", "source", "transaction_id"])
    return df[(df['date'].dt.year == year) & (df['date'].dt.month == month)]

current_date = datetime.now()
current_month_data = get_month_data(transactions_df, current_date.year, current_date.month)

# DASHBOARD PAGE
if page == "Dashboard":
    st.title("📊 Dashboard")
    st.subheader(f"{current_date.strftime('%B %Y')}")
    
    # Calculate totals
    total_budgeted = sum(budgets.values())
    total_spent = current_month_data['amount'].sum() if not current_month_data.empty else 0
    remaining = total_budgeted - total_spent
    
    # Top metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Budgeted", f"${total_budgeted:,.2f}")
    with col2:
        st.metric("Total Spent", f"${total_spent:,.2f}", 
                 delta=f"-${total_spent:,.2f}", delta_color="inverse")
    with col3:
        color = "normal" if remaining >= 0 else "inverse"
        st.metric("Remaining", f"${remaining:,.2f}", delta_color=color)
    
    st.divider()
    
    # Category breakdown
    st.subheader("Category Breakdown")
    
    if not current_month_data.empty:
        spending_by_category = current_month_data.groupby('category')['amount'].sum()
        
        for category in categories:
            budget = budgets.get(category, 0)
            spent = spending_by_category.get(category, 0)
            remaining_cat = budget - spent
            percentage = (spent / budget * 100) if budget > 0 else 0
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{category}**")
                st.progress(min(percentage / 100, 1.0))
                st.caption(f"${spent:,.2f} of ${budget:,.2f} ({percentage:.1f}%)")
            with col2:
                if remaining_cat < 0:
                    st.error(f"Over by ${abs(remaining_cat):,.2f}")
                else:
                    st.success(f"${remaining_cat:,.2f} left")
    else:
        st.info("No transactions yet this month. Add some expenses or sync your bank accounts!")
    
    st.divider()
    
    # Recent transactions
    st.subheader("Recent Transactions")
    if not current_month_data.empty:
        recent = current_month_data.sort_values('date', ascending=False).head(10)
        st.dataframe(
            recent[['date', 'description', 'category', 'amount', 'source']].style.format({'amount': '${:,.2f}'}),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No transactions to display.")

# ADD EXPENSE PAGE
elif page == "Add Expense":
    st.title("➕ Add Expense")
    
    with st.form("add_expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            expense_date = st.date_input("Date", value=datetime.now())
            expense_desc = st.text_input("Description", placeholder="e.g., Walmart groceries")
        with col2:
            expense_amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            expense_category = st.selectbox("Category", categories)
        
        submitted = st.form_submit_button("Add Expense")
        
        if submitted:
            if expense_desc and expense_amount > 0:
                new_transaction = pd.DataFrame([{
                    'date': expense_date,
                    'description': expense_desc,
                    'amount': expense_amount,
                    'category': expense_category,
                    'source': 'Manual Entry',
                    'transaction_id': f'manual-{datetime.now().timestamp()}'
                }])
                
                transactions_df = pd.concat([transactions_df, new_transaction], ignore_index=True)
                save_transactions(transactions_df)
                st.success(f"✅ Added ${expense_amount:.2f} to {expense_category}")
                st.rerun()
            else:
                st.error("Please fill in all fields")

# IMPORT CSV PAGE
elif page == "Import CSV":
    st.title("📁 Import Transactions from CSV")
    
    st.info("""
    **CSV Format Requirements:**
    - Must have columns: `date`, `description`, `amount`
    - Date format: YYYY-MM-DD or MM/DD/YYYY
    - Amount should be positive numbers
    """)
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        try:
            import_df = pd.read_csv(uploaded_file)
            
            st.write("Preview of imported data:")
            st.dataframe(import_df.head())
            
            # Column mapping
            st.subheader("Map CSV columns")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                date_col = st.selectbox("Date column", import_df.columns)
            with col2:
                desc_col = st.selectbox("Description column", import_df.columns)
            with col3:
                amount_col = st.selectbox("Amount column", import_df.columns)
            
            # Category assignment
            st.subheader("Assign categories")
            default_category = st.selectbox("Default category for all transactions", categories)
            
            if st.button("Import Transactions"):
                # Process the import
                new_transactions = pd.DataFrame({
                    'date': pd.to_datetime(import_df[date_col]),
                    'description': import_df[desc_col],
                    'amount': import_df[amount_col].abs(),
                    'category': default_category,
                    'source': 'CSV Import',
                    'transaction_id': [f'csv-{datetime.now().timestamp()}-{i}' for i in range(len(import_df))]
                })
                
                transactions_df = pd.concat([transactions_df, new_transactions], ignore_index=True)
                transactions_df = transactions_df.drop_duplicates(subset=['date', 'description', 'amount'])
                save_transactions(transactions_df)
                
                st.success(f"✅ Imported {len(new_transactions)} transactions!")
                st.rerun()
                
        except Exception as e:
            st.error(f"Error importing CSV: {str(e)}")

# PLAID SYNC PAGE
elif page == "Sync Banks (Plaid)":
    st.title("🏦 Sync Bank & Credit Card Accounts")
    
    # Debug section
    with st.expander("🔍 Debug Info - Click to expand"):
        st.write("**Plaid Configuration:**")
        st.write(f"- Client configured: {'✅ Yes' if plaid_client else '❌ No'}")
        if plaid_client:
            try:
                client_id = st.secrets.get("PLAID_CLIENT_ID", os.getenv("PLAID_CLIENT_ID", "Not set"))
                env = st.secrets.get("PLAID_ENV", os.getenv("PLAID_ENV", "Not set"))
                st.write(f"- Client ID: {client_id[:10]}... (truncated)")
                st.write(f"- Environment: {env}")
                st.write(f"- Secret configured: {'✅ Yes' if st.secrets.get('PLAID_SECRET') or os.getenv('PLAID_SECRET') else '❌ No'}")
            except Exception as e:
                st.error(f"Error reading config: {e}")
    
    if not plaid_client:
        st.error("⚠️ Plaid is not configured. Please add your Plaid credentials.")
        st.info("""
        **To set up Plaid:**
        1. Sign up at https://plaid.com/
        2. Get your Production Client ID and Secret from the dashboard
        3. Add them to your Streamlit secrets:
           - Go to your app settings on Streamlit Cloud
           - Click "Secrets"
           - Add:
             ```
             PLAID_CLIENT_ID = "your_production_client_id"
             PLAID_SECRET = "your_production_secret"
             PLAID_ENV = "production"
             ```
        4. Save and restart the app
        
        **Note:** Production mode requires approval from Plaid and may have costs.
        See: https://plaid.com/pricing/
        """)
    else:
        # Show connected accounts
        st.subheader("Connected Accounts")
        if plaid_tokens['access_tokens']:
            for i, token_info in enumerate(plaid_tokens['access_tokens']):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"🏦 {token_info.get('institution_name', 'Bank Account')} - Connected on {token_info.get('connected_date', 'Unknown')}")
                with col2:
                    if st.button(f"Remove", key=f"remove_{i}"):
                        plaid_tokens['access_tokens'].pop(i)
                        save_plaid_tokens(plaid_tokens)
                        st.success("Account removed!")
                        st.rerun()
        else:
            st.info("No accounts connected yet.")
        
        st.divider()
        
        # Connect new account
        st.subheader("Connect New Account")
        
        st.info("""
        **Production Mode:**
        - Connect your real bank accounts
        - Use your actual bank credentials
        - Transactions will sync from your real accounts
        - Data is securely encrypted by Plaid
        """)
        
        if st.button("🔗 Connect Bank Account", type="primary"):
            with st.spinner("Creating connection link..."):
                link_token = create_link_token(plaid_client)
                
                if link_token:
                    st.success("✅ Link token created successfully!")
                    
                    # Embedded Plaid Link
                    st.write("**Click the button below to connect your bank:**")
                    
                    plaid_link_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
                        <style>
                            body {{
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                                padding: 20px;
                                background: #f8f9fa;
                            }}
                            #link-button {{
                                background-color: #000000;
                                color: white;
                                padding: 14px 28px;
                                border: none;
                                border-radius: 6px;
                                font-size: 16px;
                                font-weight: 600;
                                cursor: pointer;
                                transition: all 0.2s;
                                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                            }}
                            #link-button:hover {{
                                background-color: #333333;
                                transform: translateY(-1px);
                                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                            }}
                            #link-button:active {{
                                transform: translateY(0);
                            }}
                            #link-button:disabled {{
                                background-color: #999999;
                                cursor: not-allowed;
                            }}
                            #result {{
                                margin-top: 20px;
                                padding: 16px;
                                border-radius: 6px;
                                display: none;
                            }}
                            .success {{
                                background: #d4edda;
                                border: 1px solid #c3e6cb;
                                color: #155724;
                            }}
                            .error {{
                                background: #f8d7da;
                                border: 1px solid #f5c6cb;
                                color: #721c24;
                            }}
                            .info {{
                                background: #d1ecf1;
                                border: 1px solid #bee5eb;
                                color: #0c5460;
                            }}
                            code {{
                                background: rgba(0,0,0,0.05);
                                padding: 2px 6px;
                                border-radius: 3px;
                                font-family: monospace;
                                word-break: break-all;
                            }}
                        </style>
                    </head>
                    <body>
                        <button id="link-button">🏦 Open Plaid Link</button>
                        <div id="result"></div>
                        
                        <script>
                            const linkButton = document.getElementById('link-button');
                            const resultDiv = document.getElementById('result');
                            
                            // Check if Plaid is loaded
                            if (typeof Plaid === 'undefined') {{
                                resultDiv.className = 'error';
                                resultDiv.style.display = 'block';
                                resultDiv.innerHTML = '<strong>Error:</strong> Plaid library failed to load. Check your internet connection.';
                                linkButton.disabled = true;
                            }}
                            
                            linkButton.addEventListener('click', async () => {{
                                linkButton.disabled = true;
                                linkButton.textContent = 'Opening...';
                                
                                resultDiv.className = 'info';
                                resultDiv.style.display = 'block';
                                resultDiv.innerHTML = '⏳ Initializing Plaid Link...';
                                
                                try {{
                                    console.log('Creating Plaid handler with token:', '{link_token}'.substring(0, 20) + '...');
                                    
                                    const handler = Plaid.create({{
                                        token: '{link_token}',
                                        onSuccess: (public_token, metadata) => {{
                                            console.log('Plaid success:', metadata);
                                            resultDiv.className = 'success';
                                            resultDiv.style.display = 'block';
                                            resultDiv.innerHTML = `
                                                <strong>✅ Success!</strong><br><br>
                                                <strong>Public Token:</strong><br>
                                                <code>${{public_token}}</code><br><br>
                                                <strong>Institution:</strong> ${{metadata.institution.name}}<br>
                                                <strong>Account ID:</strong> ${{metadata.accounts[0]?.id || 'N/A'}}<br><br>
                                                <em>Copy the public token above and paste it in the form below (scroll down).</em>
                                            `;
                                            linkButton.textContent = '✅ Connected!';
                                            linkButton.style.backgroundColor = '#28a745';
                                        }},
                                        onExit: (err, metadata) => {{
                                            console.log('Plaid exit:', err, metadata);
                                            if (err != null) {{
                                                resultDiv.className = 'error';
                                                resultDiv.style.display = 'block';
                                                resultDiv.innerHTML = `
                                                    <strong>❌ Error:</strong><br>
                                                    ${{err.display_message || err.error_message || 'Connection failed'}}
                                                `;
                                            }} else {{
                                                resultDiv.style.display = 'block';
                                                resultDiv.className = 'info';
                                                resultDiv.innerHTML = '<em>Connection cancelled by user.</em>';
                                            }}
                                            linkButton.disabled = false;
                                            linkButton.textContent = '🏦 Open Plaid Link';
                                        }},
                                        onLoad: () => {{
                                            console.log('Plaid loaded successfully');
                                            resultDiv.style.display = 'none';
                                            linkButton.disabled = false;
                                            linkButton.textContent = '🏦 Open Plaid Link';
                                        }},
                                        onEvent: (eventName, metadata) => {{
                                            console.log('Plaid event:', eventName, metadata);
                                        }}
                                    }});
                                    
                                    console.log('Opening Plaid handler...');
                                    handler.open();
                                }} catch (error) {{
                                    console.error('Plaid error:', error);
                                    resultDiv.className = 'error';
                                    resultDiv.style.display = 'block';
                                    resultDiv.innerHTML = `
                                        <strong>Error:</strong> ${{error.message}}<br>
                                        <small>${{error.stack || ''}}</small>
                                    `;
                                    linkButton.disabled = false;
                                    linkButton.textContent = '🏦 Open Plaid Link';
                                }}
                            }});
                        </script>
                    </body>
                    </html>
                    """
                    
                    # Display the Plaid Link component
                    st.components.v1.html(plaid_link_html, height=250, scrolling=True)
                    
                    st.divider()
                    
                    # Form to save the connection
                    st.write("**After connecting, enter the information below:**")
                    
                    with st.form("save_connection_form"):
                        public_token = st.text_input("Public Token (from above):", help="Copy the public_token that appears after connecting")
                        institution_name = st.text_input("Institution Name:", placeholder="e.g., Chase, Wells Fargo, Bank of America")
                        
                        submitted = st.form_submit_button("💾 Save Connection")
                        
                        if submitted and public_token and institution_name:
                            with st.spinner("Exchanging tokens..."):
                                access_token = exchange_public_token(plaid_client, public_token)
                                if access_token:
                                    plaid_tokens['access_tokens'].append({
                                        'access_token': access_token,
                                        'institution_name': institution_name,
                                        'connected_date': datetime.now().strftime('%Y-%m-%d')
                                    })
                                    save_plaid_tokens(plaid_tokens)
                                    st.success(f"✅ Successfully connected {institution_name}!")
                                    st.balloons()
                                    st.rerun()
                else:
                    st.error("❌ Failed to create link token. Check the error messages above.")
        
        st.divider()
        
        # Sync transactions
        st.subheader("Sync Transactions")
        st.write("Pull the latest transactions from your connected accounts (last 90 days)")
        
        if plaid_tokens['access_tokens']:
            col1, col2 = st.columns([2, 1])
            with col1:
                if st.button("🔄 Sync All Accounts", type="primary"):
                    with st.spinner("Syncing transactions..."):
                        try:
                            new_transactions = sync_plaid_transactions(plaid_client, plaid_tokens['access_tokens'])
                            
                            if new_transactions:
                                new_df = pd.DataFrame(new_transactions)
                                transactions_df = pd.concat([transactions_df, new_df], ignore_index=True)
                                transactions_df = transactions_df.drop_duplicates(subset=['transaction_id'])
                                save_transactions(transactions_df)
                                st.success(f"✅ Synced {len(new_transactions)} new transactions!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.info("No new transactions found.")
                        except Exception as e:
                            st.error(f"Error syncing: {str(e)}")
            with col2:
                st.caption(f"Last sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ No accounts connected yet. Connect a bank account first.")

# MANAGE BUDGET PAGE
elif page == "Manage Budget":
    st.title("💰 Manage Monthly Budget")
    
    st.subheader("Set Budget Limits by Category")
    
    with st.form("budget_form"):
        updated_budgets = {}
        cols = st.columns(2)
        
        for idx, category in enumerate(categories):
            with cols[idx % 2]:
                updated_budgets[category] = st.number_input(
                    f"{category}",
                    min_value=0.0,
                    value=float(budgets.get(category, 500)),
                    step=10.0
                )
        
        if st.form_submit_button("Save Budget"):
            save_budgets(updated_budgets)
            st.success("✅ Budget updated!")
            st.rerun()
    
    st.divider()
    
    # Manage categories
    st.subheader("Manage Categories")
    
    new_category = st.text_input("Add new category")
    if st.button("Add Category"):
        if new_category and new_category not in categories:
            categories.append(new_category)
            budgets[new_category] = 500
            save_categories(categories)
            save_budgets(budgets)
            st.success(f"✅ Added category: {new_category}")
            st.rerun()
        else:
            st.error("Category already exists or is empty")

# HISTORY PAGE
elif page == "History":
    st.title("📈 Historical Data")
    
    if not transactions_df.empty:
        # Month selector
        transactions_df['year_month'] = transactions_df['date'].dt.to_period('M')
        available_months = sorted(transactions_df['year_month'].unique(), reverse=True)
        
        selected_month = st.selectbox(
            "Select Month",
            available_months,
            format_func=lambda x: x.strftime('%B %Y')
        )
        
        # Filter data
        month_data = transactions_df[transactions_df['year_month'] == selected_month]
        
        # Month summary
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Spent", f"${month_data['amount'].sum():,.2f}")
        with col2:
            st.metric("Transaction Count", len(month_data))
        
        # Spending by category chart
        st.subheader("Spending by Category")
        category_spending = month_data.groupby('category')['amount'].sum().reset_index()
        fig = px.pie(category_spending, values='amount', names='category', 
                     title=f"Spending Distribution - {selected_month.strftime('%B %Y')}")
        st.plotly_chart(fig, use_container_width=True)
        
        # Trend over time
        st.subheader("Spending Trend Over Time")
        monthly_totals = transactions_df.groupby('year_month')['amount'].sum().reset_index()
        monthly_totals['year_month'] = monthly_totals['year_month'].astype(str)
        fig2 = px.line(monthly_totals, x='year_month', y='amount', 
                       title='Monthly Spending Trend', markers=True)
        fig2.update_layout(xaxis_title="Month", yaxis_title="Amount ($)")
        st.plotly_chart(fig2, use_container_width=True)
        
        # All transactions for selected month
        st.subheader("All Transactions")
        st.dataframe(
            month_data[['date', 'description', 'category', 'amount', 'source']].sort_values('date', ascending=False),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No transaction history available yet.")

# Footer
st.sidebar.divider()
st.sidebar.caption("💡 Tip: Sync your banks regularly for up-to-date data!")
if plaid_tokens['access_tokens']:
    st.sidebar.success(f"✅ {len(plaid_tokens['access_tokens'])} bank(s) connected")
