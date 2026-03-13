# Server Configuration
# TEST: Local development
# PRODUCTION: Production server

ENV = "TEST"  # TEST/PROD_DM/PROD_IP
SERVER_DOMAIN = "tasche.top"
SERVERIP = "118.25.106.35"

if ENV == "TEST":
    HOST = "0.0.0.0"
    PORT = 8000
    BASE_URL = f"http://localhost:{PORT}"
    COMPUTE_TYPE = "int16"
elif ENV == 'PROD_DM': #PRODUCT DOMAIN
    HOST = "0.0.0.0"
    PORT = 8000
    BASE_URL = f"https://{SERVER_DOMAIN}:{PORT}"  
    COMPUTE_TYPE = "int8"
else: #PROD - IP
    HOST = "0.0.0.0"
    PORT = 8000
    BASE_URL = f"http://{SERVERIP}:{PORT}" 
    COMPUTE_TYPE = "int8"
