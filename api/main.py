from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import validators
from auditor import WebsiteAuditor
from excel_generator import AuditExcelGenerator
from io import BytesIO
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Website Audit Engine API",
    description="Professional website audit service with SEO, CWV, UX, and Conversion analysis",
    version="1.0.0"
)

# Enable CORS for Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    """Request model for audit endpoint."""
    url: str
    username: str = ""
    password: str = ""


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/audit")
async def run_audit(request: AuditRequest, background_tasks: BackgroundTasks):
    """
    Run a comprehensive website audit.

    Returns an Excel file with audit results for SEO, CWV, UX, and Conversion.
    """
    try:
        # Validate URL
        url = request.url.strip()
        if not url:
            raise HTTPException(status_code=400, detail="URL cannot be empty")

        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Validate URL format
        if not validators.url(url):
            raise HTTPException(status_code=400, detail="Invalid URL format")

        logger.info(f"Starting audit for: {url}")

        # Prepare credentials if provided
        credentials = None
        if request.username and request.password:
            credentials = {
                'username': request.username,
                'password': request.password
            }
            logger.info(f"Using authenticated session for: {url}")

        # Run audit
        auditor = WebsiteAuditor(timeout=30)
        audit_results = auditor.run_full_audit(url, credentials=credentials)

        # Check for fetch errors
        if audit_results.get('error'):
            raise HTTPException(
                status_code=400,
                detail=f"Failed to fetch URL: {audit_results['error']}"
            )

        logger.info(f"Audit completed for: {url}")

        # Generate Excel file
        generator = AuditExcelGenerator(audit_results)
        excel_bytes = generator.generate()

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        domain = url.replace('https://', '').replace('http://', '').replace('/', '_')[:50]
        filename = f"audit_{domain}_{timestamp}.xlsx"

        # Return as streaming response
        return StreamingResponse(
            iter([excel_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audit error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with API documentation."""
    return {
        "name": "Website Audit Engine API",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /api/health",
            "audit": "POST /api/audit",
            "docs": "GET /docs"
        },
        "example_usage": {
            "endpoint": "POST /api/audit",
            "body": {
                "url": "https://example.com",
                "username": "(optional) login username",
                "password": "(optional) login password"
            }
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
