from get_request import app
import telegram_handler

if __name__ == '__main__':
    telegram_handler.start_bot()
    app.run()