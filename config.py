# Server Configuration
# TEST: Local development
# PRODUCTION: Production server

ENV = "PROD_DM"  # TEST/PROD_DM/PROD_IP
SERVER_DOMAIN = "tasche.top"
SERVERIP = "118.25.106.35"
HOST = "0.0.0.0"
PORT = 8000
COMPUTE_TYPE = "int8"

if ENV == "TEST":
    BASE_URL = f"http://localhost:{PORT}"
elif ENV == 'PROD_DM': #PRODUCT DOMAIN
    BASE_URL = f"https://{SERVER_DOMAIN}:{PORT}"
else: #PROD - IP
    BASE_URL = f"http://{SERVERIP}:{PORT}"
