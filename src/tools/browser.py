from src.browser.driver import get_browser_driver

def login_linkedin():
    get_browser_driver().login_interactive()

def check_session_health() -> bool:
    return get_browser_driver().check_health()

