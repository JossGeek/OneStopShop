# Backend Authentication Setup Guide

## Overview
This guide walks through setting up and using the JWT-based authentication system in the OneStopShop backend.

## Installation

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Run Database Migrations
```bash
python manage.py migrate
```

## Features

### Authentication Features
- ✅ User registration with email validation
- ✅ User login with JWT tokens (access + refresh)
- ✅ Token refresh mechanism
- ✅ User profile management
- ✅ Password change functionality
- ✅ Rate limiting on auth endpoints
- ✅ Password hashing with PBKDF2+SHA256

### User Profiles
The system supports three user profile types:
- **Student**: Default for individual learners
- **Academic staff**: For university faculty and staff
- **Company**: For company/organization representatives

## Project Structure

### Core Files

```
backend/content/
├── auth.py                 # Authentication endpoints
├── jwt_auth.py            # JWT utilities and decorators
├── models.py              # Updated User model
├── urls.py                # Auth route configuration
├── test_auth.py           # Authentication tests
└── migrations/
    └── 0004_user_first_last_profile.py
```

### Documentation

```
backend/docs/
└── AUTH_API.md           # Complete API documentation
```

## API Endpoints

All endpoints are available at `/api/auth/`:

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| POST | `/register` | Register new user | ✗ |
| POST | `/login` | Login user | ✗ |
| POST | `/refresh` | Refresh access token | ✗ |
| GET | `/me` | Get current user | ✓ |
| PATCH | `/me/update` | Update user profile | ✓ |
| POST | `/change-password` | Change password | ✓ |

For detailed API documentation, see [AUTH_API.md](./docs/AUTH_API.md)

## Development

### Running Tests
```bash
python manage.py test content.test_auth
```

### Starting Development Server
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/`

## Security Features

### Password Security
- **Algorithm**: PBKDF2 with SHA256
- **Iterations**: 100,000
- **Minimum Length**: 8 characters
- **Uniqueness**: Salted hashes ensure same passwords produce different hashes

### Token Security
- **Type**: JWT (HS256)
- **Access Token Lifetime**: 1 hour
- **Refresh Token Lifetime**: 7 days
- **Storage**: Client-side (recommended: secure httpOnly cookies)

### Rate Limiting
The following endpoints have rate limiting to prevent abuse:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/register` | 5 requests | 1 hour |
| `/login` | 10 requests | 1 hour |
| `/change-password` | 5 requests | 1 hour |

Limits are per IP address.

## Authentication Flow

### 1. User Registration
```
POST /api/auth/register
→ Returns: User object + Access & Refresh tokens
```

### 2. User Login
```
POST /api/auth/login
→ Returns: User object + Access & Refresh tokens
```

### 3. Using Access Token
```
GET /api/auth/me
Headers: Authorization: Bearer <access_token>
→ Returns: Current user information
```

### 4. Token Refresh
```
POST /api/auth/refresh
Body: { refresh_token: "..." }
→ Returns: New access & refresh tokens
```

## Environment Variables

Configure the following in your `.env` file:

```env
# Django settings
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
POSTGRES_DB=oss_db
POSTGRES_USER=oss_user
POSTGRES_PASSWORD=oss_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
CORS_ALLOW_CREDENTIALS=false
```

## Troubleshooting

### Token Validation Issues
- Ensure Authorization header format: `Bearer <token>`
- Verify token hasn't expired
- Check SECRET_KEY matches between token generation and validation

### Rate Limit Exceeded
- Wait for the rate limit window to pass (default: 1 hour per IP)
- Use backend IP in production to group requests appropriately

### Password Hashing Issues
- Don't modify password_hash directly in database
- Use the `change_password` endpoint to modify passwords
- Old hashes won't validate if schema changes

## Integration with Frontend

### Example: React/TypeScript Integration

```typescript
// Login
const response = await fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'user@example.com',
    password: 'password123'
  })
});

const data = await response.json();
const { access_token, refresh_token } = data.tokens;

// Store tokens securely
localStorage.setItem('access_token', access_token);
localStorage.setItem('refresh_token', refresh_token);

// Use token in subsequent requests
fetch('http://localhost:8000/api/auth/me', {
  headers: {
    'Authorization': `Bearer ${access_token}`
  }
});

// Refresh token when it expires
const refreshResponse = await fetch('http://localhost:8000/api/auth/refresh', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ refresh_token })
});

const newData = await refreshResponse.json();
localStorage.setItem('access_token', newData.tokens.access_token);
```

## Production Considerations

1. **HTTPS Only**: Always use HTTPS in production
2. **Secure Cookies**: Store tokens in httpOnly, secure cookies
3. **Rate Limiting**: Consider more restrictive limits or WAF rules
4. **Secret Key**: Use strong, unique SECRET_KEY in production
5. **Token Rotation**: Implement token rotation for additional security
6. **Monitoring**: Log authentication events for security audits
7. **CORS**: Configure CORS carefully to only allow frontend domain

## Support

For issues or questions:
1. Check [AUTH_API.md](./docs/AUTH_API.md) for detailed endpoint documentation
2. Review test cases in [test_auth.py](./content/test_auth.py)
3. Check Django logs for error messages

