# Financial Automation System with AI

🤖 AI-powered financial automation system for the Brazilian market that combines conversational AI, accounting platform integration, electronic signatures, and intelligent delinquency analysis.

## 📋 Overview

This system provides a complete financial automation solution that streamlines contract generation, client management, and payment monitoring through intelligent integrations:

- **Conversational AI**: Natural language data collection using Claude AI
- **Accounting Integration**: Automatic client and financial data synchronization with Conta Azul
- **Electronic Signatures**: Legally-valid document signing through Autentique
- **Delinquency Analysis**: Intelligent payment pattern analysis and risk detection
- **Real-time Monitoring**: Dashboard for financial KPIs and operational insights

## ✨ Features

### Core Capabilities

- **🗣️ AI-Powered Data Collection**
  - Natural conversational interface for gathering contract information
  - Multi-turn conversations that guide users through data collection
  - Automatic validation and structured data extraction

- **📄 Automated Contract Generation**
  - Generate professional PDF contracts from conversational data
  - Customizable HTML templates with CSS styling support
  - Automatic variable substitution and formatting

- **🔄 Conta Azul Integration**
  - OAuth 2.0 authenticated connection to Conta Azul platform
  - Automatic client data synchronization (hourly)
  - Financial data import (daily)
  - Automatic token refresh handling

- **✍️ Electronic Signature Workflow**
  - Submit contracts to Autentique for signature collection
  - Real-time signature status tracking
  - Automatic retrieval of signed documents
  - Email notifications to signers

- **📊 Delinquency Analysis**
  - Automated payment pattern analysis
  - Risk score calculation for clients
  - Overdue payment detection and alerts
  - Historical trend analysis

- **📈 Monitoring Dashboard**
  - Real-time KPI visualization
  - Active contracts tracking
  - Pending signatures monitoring
  - Overdue payment alerts

## 🏗️ Architecture

### Tech Stack

- **Backend Framework**: FastAPI (Python 3.9-3.12)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **AI Integration**: Anthropic Claude API
- **Accounting**: Conta Azul REST API (OAuth 2.0)
- **Signatures**: Autentique GraphQL API
- **Background Jobs**: APScheduler
- **PDF Generation**: WeasyPrint
- **Migrations**: Alembic

### Project Structure

```
agent-financeiro-aisatec/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Environment configuration
│   ├── database.py                # SQLAlchemy database setup
│   ├── models/                    # Database models (ORM)
│   │   ├── client.py              # Client/customer model
│   │   ├── contract.py            # Contract model
│   │   ├── financial_record.py   # Financial transactions
│   │   ├── signature.py           # Signature tracking
│   │   └── integration_token.py  # OAuth token storage
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── client.py
│   │   ├── contract.py
│   │   └── financial.py
│   ├── api/                       # API route handlers
│   │   ├── conversation.py        # Claude conversational endpoints
│   │   ├── clients.py             # Client management
│   │   ├── contracts.py           # Contract operations
│   │   ├── signatures.py          # Signature workflow
│   │   ├── dashboard.py           # Dashboard data
│   │   └── auth.py                # OAuth authentication
│   ├── services/                  # Business logic layer
│   │   ├── claude_service.py      # Claude API integration
│   │   ├── conta_azul_service.py  # Conta Azul OAuth2 client
│   │   ├── autentique_service.py  # Autentique GraphQL client
│   │   ├── contract_generator.py  # Contract generation logic
│   │   └── delinquency_analyzer.py # Payment analysis engine
│   ├── background/                # Background job definitions
│   │   ├── sync_clients.py        # Scheduled client sync
│   │   └── sync_financial.py     # Scheduled financial data sync
│   └── templates/                 # Contract templates
│       └── default_contract.html  # Base contract template
├── tests/                         # Test suite
│   ├── test_services/
│   └── test_api/
├── alembic/                       # Database migrations
│   └── versions/
├── .env.example                   # Environment variable template
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## 🚀 Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

- **Python**: Version 3.9, 3.10, 3.11, or 3.12 (NOT 3.13 - Anthropic SDK incompatibility)
- **PostgreSQL**: Version 12 or higher
- **Git**: For version control

You'll also need API credentials for:
- [Anthropic Claude](https://console.anthropic.com/) - AI conversational assistant
- [Conta Azul](https://portaldevs.contaazul.com/) - Brazilian accounting platform
- [Autentique](https://www.autentique.com.br/) - Electronic signature service

#### Checking Python Version

```bash
python --version  # Should show 3.9.x, 3.10.x, 3.11.x, or 3.12.x
```

If you need to install a compatible Python version:
- **macOS**: `brew install python@3.11`
- **Ubuntu/Debian**: `sudo apt install python3.11`
- **Windows**: Download from [python.org](https://www.python.org/downloads/)

### Installation

1. **Clone the repository**

```bash
git clone <repository-url>
cd agent-financeiro-aisatec
```

2. **Create and activate a virtual environment**

```bash
# Create virtual environment with Python 3.11 (or compatible version)
python3.11 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

3. **Install dependencies**

```bash
# Upgrade pip
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt
```

**Note for WeasyPrint**: WeasyPrint requires system dependencies for PDF generation:

- **macOS**: `brew install cairo pango gdk-pixbuf libffi`
- **Ubuntu/Debian**: `sudo apt install libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev`
- **Windows**: See [WeasyPrint documentation](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows)

4. **Set up PostgreSQL database**

```bash
# Create database
createdb financial_automation

# Or using psql:
psql -U postgres
CREATE DATABASE financial_automation;
\q
```

5. **Configure environment variables**

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

See the [Configuration](#configuration) section below for details on all required variables.

6. **Run database migrations**

```bash
# Apply all migrations
alembic upgrade head

# Verify migrations
alembic current
```

7. **Start the application**

```bash
# Development mode (with auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

The application will be available at:
- **API**: http://localhost:8000
- **Interactive API Docs**: http://localhost:8000/docs
- **ReDoc Documentation**: http://localhost:8000/redoc

## ⚙️ Configuration

### Environment Variables

All configuration is managed through environment variables. Copy `.env.example` to `.env` and update with your credentials:

#### Application Settings

```bash
APP_NAME=Financial Automation System
DEBUG=true                    # Set to false in production
API_HOST=0.0.0.0
API_PORT=8000
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]
```

#### Database Configuration

```bash
DATABASE_URL=postgresql://username:password@localhost:5432/financial_automation
```

Replace `username` and `password` with your PostgreSQL credentials.

#### Anthropic Claude API

```bash
ANTHROPIC_API_KEY=sk-ant-...  # Get from console.anthropic.com
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

**Getting your API key:**
1. Sign up at [console.anthropic.com](https://console.anthropic.com/)
2. Navigate to API Keys section
3. Create a new API key
4. Copy and paste into `.env`

#### Conta Azul API

```bash
CONTA_AZUL_CLIENT_ID=your_client_id_from_portal
CONTA_AZUL_CLIENT_SECRET=your_client_secret_from_portal
CONTA_AZUL_REDIRECT_URI=http://localhost:8000/api/auth/conta-azul/callback
CONTA_AZUL_API_BASE_URL=https://api.contaazul.com
```

**Setting up Conta Azul integration:**
1. Register your application at [portaldevs.contaazul.com](https://portaldevs.contaazul.com/)
2. Create a new app to get Client ID and Client Secret
3. Configure redirect URI: `http://localhost:8000/api/auth/conta-azul/callback`
4. Request scopes: `sales`, `customers`, `financial`

#### Autentique API

```bash
AUTENTIQUE_API_KEY=your_api_key_from_dashboard
AUTENTIQUE_API_URL=https://api.autentique.com.br/v2/graphql
AUTENTIQUE_RATE_LIMIT=60  # Requests per minute
```

**Getting your Autentique API key:**
1. Sign up at [autentique.com.br](https://www.autentique.com.br/)
2. Access your dashboard
3. Navigate to API settings
4. Generate a new API key
5. Copy and paste into `.env`

### Security Best Practices

⚠️ **IMPORTANT**:
- **Never commit `.env` file** to version control (already in `.gitignore`)
- **Use strong passwords** for database credentials
- **Rotate API keys periodically** (every 90 days recommended)
- **Set `DEBUG=false`** in production environments
- **Use HTTPS** in production (enable SSL/TLS)
- **Restrict `ALLOWED_ORIGINS`** to your actual frontend domains in production

## 🔧 Usage

### OAuth Flow - Connecting Conta Azul

Before you can sync data from Conta Azul, you must complete the OAuth 2.0 authorization flow:

1. **Start the authorization flow**

```bash
# Navigate to the authorization endpoint
curl http://localhost:8000/api/auth/conta-azul/authorize
```

Or visit in your browser: http://localhost:8000/api/auth/conta-azul/authorize

2. **Authorize the application**

You'll be redirected to Conta Azul's login page. Sign in and authorize the application to access your data.

3. **Automatic token storage**

After authorization, you'll be redirected back to the callback URL, and the access token will be automatically stored in the database.

4. **Verify connection**

```bash
# Check token status
curl http://localhost:8000/api/clients/sync
```

### Starting a Conversation

Initiate a conversational flow to collect contract data:

```bash
# Start new conversation
curl -X POST http://localhost:8000/api/conversation/start \
  -H "Content-Type: application/json"

# Send a message
curl -X POST http://localhost:8000/api/conversation/{conversation_id}/message \
  -H "Content-Type: application/json" \
  -d '{"message": "I need to create a contract for my client"}'
```

### Generating Contracts

Once all data is collected through the conversation:

```bash
# Generate contract from conversation
curl -X POST http://localhost:8000/api/contracts/generate \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "uuid-here"}'

# Download contract PDF
curl http://localhost:8000/api/contracts/{contract_id}/download --output contract.pdf
```

### Submitting for Signature

Send a contract to Autentique for electronic signatures:

```bash
# Submit contract for signature
curl -X POST http://localhost:8000/api/signatures/submit \
  -H "Content-Type: application/json" \
  -d '{
    "contract_id": "uuid-here",
    "signers": [
      {"email": "client@example.com", "name": "Client Name"}
    ]
  }'

# Check signature status
curl http://localhost:8000/api/signatures/{signature_id}/status
```

## 📊 Background Jobs

The system runs automated background jobs for data synchronization:

### Client Synchronization

- **Frequency**: Every hour
- **Purpose**: Sync client data from Conta Azul
- **What it does**:
  - Fetches new and updated clients from Conta Azul
  - Updates local database with latest client information
  - Uses CPF/CNPJ as natural key to prevent duplicates

### Financial Data Synchronization

- **Frequency**: Daily at 2:00 AM
- **Purpose**: Import invoices, payments, and receivables
- **What it does**:
  - Fetches financial transactions from Conta Azul
  - Updates payment status and dates
  - Performs incremental sync (only new data since last sync)

### Job Monitoring

Background jobs are managed by APScheduler and run automatically when the application starts. Monitor job execution through logs:

```bash
# View application logs
tail -f logs/app.log

# Check specific job execution
grep "sync_clients" logs/app.log
```

Jobs are configured in `app/main.py` and scheduled during application startup.

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_services/test_claude.py

# Run with verbose output
pytest -v

# Run async tests
pytest tests/test_api/ -v
```

### Test Structure

- `tests/test_services/` - Unit tests for service layer
- `tests/test_api/` - Integration tests for API endpoints
- `tests/test_integration/` - End-to-end workflow tests

### Manual API Testing

Use the interactive API documentation:

1. Navigate to http://localhost:8000/docs
2. Click "Try it out" on any endpoint
3. Fill in parameters and execute requests
4. View responses in real-time

Alternatively, use tools like:
- **Postman**: Import OpenAPI schema from `/openapi.json`
- **cURL**: Use command-line examples from documentation
- **HTTPie**: `http GET localhost:8000/health`

## 📚 API Documentation

The API is fully documented using OpenAPI (Swagger) specification:

- **Interactive Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### Key Endpoints

#### Health Check
- `GET /health` - Application health status

#### Conversation
- `POST /api/conversation/start` - Start new conversation
- `POST /api/conversation/{id}/message` - Send message
- `GET /api/conversation/{id}` - Get conversation history

#### Clients
- `GET /api/clients/` - List clients
- `GET /api/clients/{id}` - Get client details
- `POST /api/clients/` - Create client
- `POST /api/clients/sync` - Trigger Conta Azul sync

#### Contracts
- `POST /api/contracts/generate` - Generate contract from conversation
- `GET /api/contracts/{id}` - Get contract details
- `GET /api/contracts/{id}/download` - Download PDF

#### Signatures
- `POST /api/signatures/submit` - Submit contract to Autentique
- `GET /api/signatures/{id}/status` - Check signature status

#### Dashboard
- `GET /api/dashboard/metrics` - Get KPIs and metrics

#### Authentication
- `GET /api/auth/conta-azul/authorize` - Start OAuth flow
- `GET /api/auth/conta-azul/callback` - OAuth callback

## 🗄️ Database

### Migrations

Database schema is managed with Alembic:

```bash
# Create a new migration
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current

# View migration history
alembic history
```

### Database Schema

Main tables:
- `clients` - Client/customer information
- `contracts` - Generated contracts
- `financial_records` - Invoices and payments
- `signatures` - Electronic signature tracking
- `integration_tokens` - OAuth access/refresh tokens
- `conversations` - Conversation history and state

### Manual Database Access

```bash
# Connect to database
psql -U username -d financial_automation

# Useful queries
SELECT COUNT(*) FROM clients;
SELECT * FROM integration_tokens WHERE service = 'conta_azul';
SELECT status, COUNT(*) FROM signatures GROUP BY status;
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Import Error: "No module named 'anthropic'"

**Solution**: Ensure you're using Python 3.9-3.12 and have activated the virtual environment:

```bash
python --version  # Check version
source venv/bin/activate  # Activate venv
pip install -r requirements.txt  # Reinstall dependencies
```

#### 2. Database Connection Error

**Solution**: Verify PostgreSQL is running and credentials are correct:

```bash
# Check PostgreSQL status
# macOS: brew services list
# Linux: sudo systemctl status postgresql

# Test connection
psql -U username -d financial_automation

# Verify DATABASE_URL in .env matches your setup
```

#### 3. Conta Azul OAuth Error: "Invalid redirect URI"

**Solution**: Ensure redirect URI in your Conta Azul app configuration exactly matches the one in `.env`:

```bash
CONTA_AZUL_REDIRECT_URI=http://localhost:8000/api/auth/conta-azul/callback
```

#### 4. Autentique Rate Limit Error

**Solution**: The system implements automatic rate limiting. If you hit the limit during testing:

- Wait 60 seconds before retrying
- Reduce request frequency in tests
- Check `AUTENTIQUE_RATE_LIMIT` is set to 60

#### 5. WeasyPrint PDF Generation Fails

**Solution**: Install system dependencies:

```bash
# macOS
brew install cairo pango gdk-pixbuf libffi

# Ubuntu/Debian
sudo apt install libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev

# Then reinstall WeasyPrint
pip uninstall weasyprint
pip install weasyprint
```

#### 6. Background Jobs Not Running

**Solution**: Background jobs are scheduled on application startup. Verify in logs:

```bash
# Check logs for scheduler messages
grep "scheduler" logs/app.log
grep "APScheduler" logs/app.log

# Ensure application started successfully
tail -f logs/app.log
```

### Debug Mode

Enable detailed logging:

```bash
# In .env
DEBUG=true

# Restart application
uvicorn app.main:app --reload --log-level debug
```

### Getting Help

If you encounter issues not covered here:

1. Check the application logs: `logs/app.log`
2. Review API documentation: http://localhost:8000/docs
3. Verify environment variables: `cat .env` (never share actual credentials)
4. Check database migrations: `alembic current`

## 🚀 Production Deployment

### Pre-deployment Checklist

Before deploying to production:

- [ ] Set `DEBUG=false` in environment
- [ ] Use strong, unique database password
- [ ] Configure production `DATABASE_URL`
- [ ] Update `ALLOWED_ORIGINS` to production domains
- [ ] Enable HTTPS/TLS with valid SSL certificate
- [ ] Use production API keys (not sandbox/test keys)
- [ ] Set up database backups (automated daily recommended)
- [ ] Configure monitoring and alerting
- [ ] Set up centralized logging
- [ ] Review and harden firewall rules
- [ ] Enable database encryption at rest
- [ ] Configure rate limiting on endpoints
- [ ] Set up health check monitoring
- [ ] Document disaster recovery procedures

### Deployment Options

#### Option 1: Docker Deployment

```dockerfile
# Example Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

#### Option 2: Traditional Server

```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Or use systemd service
sudo systemctl enable financial-automation
sudo systemctl start financial-automation
```

#### Option 3: Cloud Platforms

- **AWS**: Elastic Beanstalk, ECS, or Lambda
- **Google Cloud**: Cloud Run, App Engine, or Compute Engine
- **Heroku**: `git push heroku main`
- **DigitalOcean**: App Platform or Droplets

### Production Configuration

```bash
# Production .env example
APP_NAME=Financial Automation System
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000
ALLOWED_ORIGINS=["https://yourdomain.com"]

# Use managed PostgreSQL service
DATABASE_URL=postgresql://user:pass@prod-db.example.com:5432/financial_automation

# Production API keys
ANTHROPIC_API_KEY=sk-ant-prod-...
CONTA_AZUL_CLIENT_ID=prod_client_id
CONTA_AZUL_CLIENT_SECRET=prod_secret
AUTENTIQUE_API_KEY=prod_api_key
```

### Monitoring

Set up monitoring for:
- Application uptime and health
- API response times
- Background job execution
- Database connection pool
- External API call success rates
- Error rates and types

Recommended tools:
- **Sentry** - Error tracking
- **Datadog** - Infrastructure monitoring
- **Prometheus + Grafana** - Metrics visualization
- **CloudWatch** - AWS monitoring

## 📝 License

[Add your license information here]

## 👥 Contributing

[Add contribution guidelines here]

## 📞 Support

For questions or issues:
- Check the [Troubleshooting](#troubleshooting) section
- Review API documentation at `/docs`
- Open an issue on GitHub
- Contact support: [Add contact information]

---

**Built with FastAPI, Claude AI, and ❤️ for the Brazilian market**
