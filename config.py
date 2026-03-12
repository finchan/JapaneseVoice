# Server Configuration
# TEST: Local development
# PRODUCTION: Production server

ENV = "PROD"  # Change to "PRODUCTION" for production deployment
SERVER_IP = "118.25.106.35"
if ENV == "TEST":
    HOST = "0.0.0.0"
    PORT = 8000
    BASE_URL = f"http://localhost:{PORT}"
else:
    HOST = "0.0.0.0"
    PORT = 8000
    BASE_URL = f"http://{SERVER_IP}:{PORT}"  # Replace with actual domain for production
