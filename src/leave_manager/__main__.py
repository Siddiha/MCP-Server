"""Start the server: `python -m leave_manager` or `leave-manager`."""
from .config import configure_logging, load_settings
from .server import create_server
from .service import LeaveService
from .storage import LeaveStore


def main() -> None:
    """Wire the pieces together and serve over stdio"""
    settings = load_settings()
    configure_logging(settings.log_level)

    store = LeaveStore(settings.data_file)
    service = LeaveService(store, default_balance=settings.default_balance)
    create_server(service).run()


if __name__ == "__main__":
    main()
