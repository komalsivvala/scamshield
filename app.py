"""Entry point: `python app.py` serves ScamShield on port 7860 (also used by the Hugging Face Space)."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "7860")), proxy_headers=True, forwarded_allow_ips="*")
