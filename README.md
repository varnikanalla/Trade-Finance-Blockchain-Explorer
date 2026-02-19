# Trade Finance Blockchain Explorer

A comprehensive platform for transparent, tamper-evident tracking of trade finance artifacts with risk insights and compliance reporting.

## 📋 Project Overview

The Trade Finance Blockchain Explorer provides secure document management, ledger-style tracking, and risk assessment for trade finance operations. Built with FastAPI backend and designed for React frontend integration.

### Key Features

✅ **Document Repository** - Secure storage with SHA-256 hashing  
✅ **Ledger Explorer** - Immutable audit trail of all document lifecycle events  
✅ **Tamper Detection** - Automated integrity checks with alert system  
✅ **Risk Scoring** - Multi-factor analysis combining internal + external data  
✅ **Analytics Dashboards** - Comprehensive KPIs and visualizations  
✅ **Export Capabilities** - CSV and PDF reports for compliance  
✅ **Multi-role Access** - Bank, Corporate, Auditor, Admin roles  
✅ **External Data Integration** - UNCTAD, WTO, BIS, World Bank APIs  

## 🏗️ Tech Stack

**Backend:**
- FastAPI (Python web framework)
- SQLModel / SQLAlchemy (ORM)
- PostgreSQL (production) / SQLite (development)
- JWT Authentication
- Celery (background tasks)
- Redis (task queue)

**External Integrations:**
- UNCTAD (trade statistics)
- WTO (trade policy)
- BIS (banking data)
- World Bank (economic indicators)

**Export/Reporting:**
- ReportLab (PDF generation)
- CSV exports
- Streaming responses

**Frontend** (planned):
- React.js
- Tailwind CSS
- Chart.js / Recharts

## 📚 Database Schema

### Core Tables

**Users**
- Multi-role support (bank, corporate, auditor, admin)
- Organization scoping
- JWT authentication

**Documents**
- Multiple document types (LOC, Invoice, Bill of Lading, PO, COO, Insurance Cert)
- SHA-256 hash verification
- S3-compatible storage integration

**LedgerEntries**
- Immutable audit trail
- Actions: ISSUED, AMENDED, SHIPPED, RECEIVED, PAID, CANCELLED, VERIFIED
- JSONB metadata support

**TradeTransactions**
- Buyer/seller tracking
- Multi-currency support
- Status workflow (pending → in_progress → completed/disputed)

**RiskScores**
- 0-100 risk score with rationale
- Automated calculation
- Historical tracking

**IntegrityAlerts**
- Hash mismatch detection
- Severity levels
- Resolution workflow

## 🚀 Getting Started

### Prerequisites

```bash
Python 3.10+
PostgreSQL 14+ (or SQLite for development)
Redis 6+ (for background tasks)
```

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd trade_finance
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements_full.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database**
```bash
# Database will be created automatically on first run
python -m app.database
```

### Running the Application

**Development Server:**
```bash
# Start API server
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info

# Start Celery beat scheduler (separate terminal)
celery -A app.workers.celery_app beat --loglevel=info
```

**Access API Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📖 API Documentation

### Authentication

```bash
# Register new user
POST /auth/register
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "secure_password",
  "role": "corporate",
  "org_name": "ACME Corp"
}

# Login
POST /auth/login
{
  "email": "john@example.com",
  "password": "secure_password"
}
# Returns: {"access_token": "...", "token_type": "bearer"}
```

### Document Management

```bash
# Upload document
POST /documents/
{
  "doc_type": "INVOICE",
  "doc_number": "INV-2024-001",
  "file": <multipart_file>,
  "issued_at": "2024-01-15T00:00:00Z"
}

# Get document
GET /documents/{document_id}

# List documents
GET /documents/?owner_id=5&doc_type=INVOICE
```

### Ledger Operations

```bash
# Add ledger entry
POST /ledger/
{
  "document_id": 123,
  "action": "VERIFIED",
  "metadata": {"notes": "Document verified by auditor"}
}

# Get document history
GET /ledger/document/{document_id}

# Verify hash chain
GET /ledger/verify/{document_id}
```

### Trade Transactions

```bash
# Create transaction
POST /trade/transactions
{
  "buyer_id": 5,
  "seller_id": 7,
  "amount": 100000.00,
  "currency": "USD"
}

# Update status
PUT /trade/transactions/{transaction_id}/status
{
  "status": "completed"
}

# Get transactions
GET /trade/transactions?status=pending
```

### Risk Assessment (Week 7)

```bash
# Calculate risk score
POST /api/risk/calculate/{user_id}

# Get all risk scores
GET /api/risk/scores?limit=100

# Get high-risk entities
GET /api/risk/high-risk-entities?threshold=60

# Get external country data
GET /api/external-data/country/USA

# Check sanctions
GET /api/external-data/sanctions-check?entity_name=ACME&country=USA
```

### Analytics (Week 8)

```bash
# Dashboard statistics
GET /api/analytics/dashboard

# Transaction trends
GET /api/analytics/transactions/trends?days=30

# Risk distribution
GET /api/analytics/risk/distribution

# Document breakdown
GET /api/analytics/documents/by-type

# Top traders
GET /api/analytics/top-traders?limit=10
```

### Exports (Week 8)

```bash
# Export users to CSV
GET /api/export/users.csv

# Export transactions to CSV
GET /api/export/transactions.csv?days=90

# Export risk scores to CSV
GET /api/export/risk-scores.csv

# Generate compliance PDF report
GET /api/export/compliance-report.pdf
```

## 📅 Development Timeline

### ✅ Milestone 1 (Weeks 1-2): Auth & Org Setup
- JWT authentication system
- User roles and permissions
- Organization scoping
- Base API structure

### ✅ Milestone 2 (Weeks 3-4): Documents & Ledger
- Document upload with S3 storage
- SHA-256 hash generation
- Ledger entry system
- Hash chain verification UI

### ✅ Milestone 3 (Weeks 5-6): Transactions & Integrity
- Trade transaction workflows
- Buyer/seller tracking
- Celery-based integrity checks
- Automated mismatch alerts

### ✅ Milestone 4 (Weeks 7-8): Risk & Analytics
- Risk scoring engine
- External data integration (UNCTAD, WTO, BIS)
- Analytics dashboards
- CSV/PDF exports
- Compliance reporting

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_week7_week8.py -v

# Run specific test
pytest tests/test_week7_week8.py::test_calculate_risk_score -v
```

## 🔐 Security

### Authentication
- JWT tokens with expiration
- Password hashing (bcrypt)
- Role-based access control (RBAC)

### Data Protection
- Document hash verification
- Tamper detection
- Audit logging
- Input validation and sanitization

### External APIs
- API keys stored in environment variables
- Rate limiting
- Circuit breakers for failing services
- Request timeouts

## 📊 Monitoring & Logging

**Recommended Tools:**
- **Application Monitoring**: Datadog, New Relic, or Sentry
- **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **Metrics**: Prometheus + Grafana
- **APM**: Application Performance Monitoring

**Key Metrics to Track:**
- API response times
- Error rates
- Risk calculation performance
- External API latency
- Export generation time
- Database query performance

## 🚢 Deployment

### Docker (Recommended)

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements_full.txt .
RUN pip install --no-cache-dir -r requirements_full.txt

COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build image
docker build -t trade-finance-api .

# Run container
docker run -p 8000:8000 --env-file .env trade-finance-api
```

### Production Checklist

- [ ] Configure production database (PostgreSQL)
- [ ] Set up Redis cluster for Celery
- [ ] Configure S3/object storage for documents
- [ ] Enable HTTPS/TLS
- [ ] Set up load balancer
- [ ] Configure CORS for production domains
- [ ] Set up monitoring and alerting
- [ ] Configure backup and disaster recovery
- [ ] Implement rate limiting
- [ ] Set up CI/CD pipeline
- [ ] Configure logging aggregation
- [ ] Register external API keys (UNCTAD, WTO, etc.)
- [ ] Set up scheduled tasks (Celery beat)
- [ ] Configure environment-specific settings

## 🌐 External API Integration

### Production Setup

Replace mock data with real API calls:

```python
# Example: Real World Bank API
async def get_worldbank_real(country_code: str):
    async with httpx.AsyncClient() as client:
        url = f"https://api.worldbank.org/v2/country/{country_code}/indicator/NY.GDP.MKTP.KD.ZG"
        params = {"format": "json", "per_page": 1}
        response = await client.get(url, params=params)
        return response.json()
```

**Required API Keys:**
- World Bank: No key required (public API)
- UNCTAD: Contact for API access
- WTO: Register at https://api.wto.org/
- ExchangeRate API: Get key from exchangerate-api.com
- Sanctions Lists: ComplyAdvantage or Refinitiv

## 📱 Frontend Integration

### React Example

```javascript
import { useState, useEffect } from 'react';

function Dashboard() {
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    fetch('/api/analytics/dashboard', {
      headers: {'Authorization': `Bearer ${token}`}
    })
      .then(res => res.json())
      .then(data => setStats(data));
  }, []);
  
  if (!stats) return <div>Loading...</div>;
  
  return (
    <div className="grid grid-cols-4 gap-4">
      <StatCard title="Users" value={stats.total_users} />
      <StatCard title="Documents" value={stats.total_documents} />
      <StatCard title="Transactions" value={stats.total_transactions} />
      <StatCard title="High Risk" value={stats.high_risk_users} />
    </div>
  );
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Team

**Project Type**: Educational / Portfolio Project  
**Course**: Trade Finance Blockchain Development  
**Duration**: 8 weeks  

## 📞 Support

For issues and questions:
- **API Documentation**: `/docs` endpoint
- **Issues**: GitHub Issues
- **Email**: support@example.com

## 🔄 Version History

- **v1.0.0** (Week 8) - Full implementation with risk scoring and analytics
- **v0.9.0** (Week 6) - Integrity checks and automated monitoring
- **v0.8.0** (Week 5) - Trade transactions
- **v0.7.0** (Week 4) - Ledger explorer
- **v0.6.0** (Week 3) - Document management
- **v0.5.0** (Week 2) - Role-based access
- **v0.1.0** (Week 1) - Initial authentication system

## 🎯 Future Roadmap

- [ ] Machine learning for risk prediction
- [ ] Real-time WebSocket notifications
- [ ] Mobile app (React Native)
- [ ] Blockchain integration (Ethereum/Hyperledger)
- [ ] Advanced analytics (predictive models)
- [ ] Multi-language support
- [ ] White-label customization
- [ ] API marketplace for external integrations

---

**Built with ❤️ using FastAPI and modern Python**
