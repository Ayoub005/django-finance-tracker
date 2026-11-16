import webview

if __name__ == '__main__':
    # Launches your live Render app in a dedicated desktop window
    webview.create_window(
        'Finance Tracker', 
        'https://django-finance-tracker-yo0z.onrender.com',
        width=1200,
        height=800
    )
    webview.start()