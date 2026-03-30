from seleniumbase import Driver
import time

PARSE_URL = "https://www.wildberries.ru/"
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
TOKEN_NAME = "x_wbaas_token"

class WBCookies:
    def __init__(self):
        self.url = PARSE_URL
        self.user_agent = USER_AGENT
        self.token_name = TOKEN_NAME


    def get_token(self) -> str:
        driver = Driver(
            uc=True,
            headed=False,
            headless=True,
            agent=self.user_agent
        )
        try:
            driver.open(self.url)
            for i in range(3):
                cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})
                for cookie in cookies.get("cookies"):
                    if cookie.get("name") == self.token_name:
                        print("Cookie успешно получены!")
                        return cookie.get("value")
                time.sleep(5)
            return None
        finally:
            driver.quit()


def get_token() -> str:
    return WBCookies().get_token()



if __name__ == "__main__":
    token = WBCookies().get_token()
    print(token)
