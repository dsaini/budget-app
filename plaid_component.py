import streamlit.components.v1 as components

def plaid_link(link_token):
    """Render Plaid Link component"""
    plaid_link_html = f"""
    <html>
    <head>
        <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    </head>
    <body>
        <button id="link-button" style="
            background-color: #000000;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
            font-family: sans-serif;
        ">Connect a Bank Account</button>
        
        <div id="result" style="margin-top: 20px; font-family: sans-serif;"></div>
        
        <script>
            const linkButton = document.getElementById('link-button');
            const resultDiv = document.getElementById('result');
            
            linkButton.addEventListener('click', async () => {{
                const handler = Plaid.create({{
                    token: '{link_token}',
                    onSuccess: (public_token, metadata) => {{
                        resultDiv.innerHTML = `
                            <div style="background: #d4edda; padding: 15px; border-radius: 4px; color: #155724;">
                                <strong>Success!</strong><br>
                                Public Token: <code style="background: #c3e6cb; padding: 2px 6px; border-radius: 3px;">${{public_token}}</code><br>
                                Institution: <strong>${{metadata.institution.name}}</strong><br><br>
                                Copy the public token above and paste it in the app.
                            </div>
                        `;
                        
                        // Send data back to Streamlit
                        window.parent.postMessage({{
                            type: 'plaid-success',
                            public_token: public_token,
                            institution_name: metadata.institution.name
                        }}, '*');
                    }},
                    onExit: (err, metadata) => {{
                        if (err != null) {{
                            resultDiv.innerHTML = `
                                <div style="background: #f8d7da; padding: 15px; border-radius: 4px; color: #721c24;">
                                    <strong>Error:</strong> ${{err.error_message}}
                                </div>
                            `;
                        }}
                    }}
                }});
                
                handler.open();
            }});
        </script>
    </body>
    </html>
    """
    
    components.html(plaid_link_html, height=300)
