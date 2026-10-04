"""
MARkit - Autonomous Indian Stock Market Trading Desk Launcher.
Starts the FastAPI server with live market feeds, agent reasoning, and web dashboard.
"""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    print("=" * 65)
    print("  🚀 MARkit: Autonomous Indian Stock Market AI Trading Agent")
    print("  📈 Paper Trading Simulation (Real-Time NSE Feeds)")
    print("  ⏰ Market Schedule: 09:15 - 15:30 IST (Asia/Kolkata)")
    print("  🌐 Dashboard running at: http://127.0.0.1:8000")
    print("=" * 65)
    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, reload=False)
