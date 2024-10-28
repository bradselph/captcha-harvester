import harvester
import logging
from threading import Event

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def handle_captcha_response(response):
    """Callback for handling solved captchas"""
    logging.info(f"Got captcha response: {response['response'][:30]}...")

def main():
    url = 'https://www.google.com/recaptcha/api2/demo'

    logging.info("Fetching sitekey...")
    sitekey = harvester.Harvester.get_sitekey(url)
    if not sitekey:
        logging.error("Failed to get sitekey")
        return

    logging.info(f"Found sitekey: {sitekey}")

    manager = harvester.HarvesterManager(response_callback=handle_captcha_response)

    manager.add_harvester(
        harvester.Harvester(
            url=url,
            sitekey=sitekey
        )
    )

    manager.add_harvester(
        harvester.Harvester(
            url=url,
            sitekey=sitekey,
            log_in=True,
            open_youtube=True
        )
    )

    logging.info("Starting harvesters...")
    manager.start_harvesters()

    try:
        logging.info("Running main loop - Press Ctrl+C to stop")
        manager.main_loop()
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        manager.stop()

if __name__ == '__main__':
    main()
