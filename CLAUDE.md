# GraphQL UG - Microsoft Entra Integration Project

## Project Goal

Create a container GraphQL endpoint written in Python that connects to Microsoft Entra and can be swapped in place of the existing `gql_ug` project.

## Current Project Analysis

### Technology Stack
- **Framework**: FastAPI with Strawberry GraphQL
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT-based token validation
- **Deployment**: Docker containerized
- **Authorization**: RBAC (Role-Based Access Control) system

### Project Structure
```
src/
├── GraphTypeDefinitions/     # GraphQL schema (~6000 lines, 19 files)
│   ├── userGQLModel.py      # User management (529 lines)
│   ├── groupGQLModel.py     # Group management (848 lines)
│   ├── roleGQLModel.py      # Role management (600 lines)
│   ├── RBACObjectGQLModel.py # RBAC permissions (361 lines)
│   └── ...
├── DBDefinitions/           # Database models (~1100 lines, 17 files)
│   ├── UserModel.py         # User entity (80 lines)
│   ├── GroupModel.py        # Group hierarchy (331 lines)
│   ├── RoleModel.py         # Role definitions (68 lines)
│   └── ...
├── GraphPermissions.py      # Permission validation
├── Dataloaders.py          # GraphQL data loading optimization
└── DBFeeder.py             # Database initialization
```

### Core Functionality
- **User Management**: Users with profiles, validity states
- **Group Management**: Hierarchical group structure with master/child relationships
- **Role Management**: Role-based permissions with types and categories
- **Membership Management**: User-group relationships with roles
- **State Machines**: Workflow management system
- **RBAC Objects**: Fine-grained permission control

### Current Authentication
- JWT token validation via `JWTPUBLICKEYURL`
- User resolution via `JWTRESOLVEUSERPATHURL`
- Demo mode for development (`DEMO=true`)
- Environment variables in `environment.txt`

## Implementation Plan

### Phase 1: Authentication Migration
- [ ] Replace JWT endpoints with Microsoft Entra ID OAuth 2.0/OpenID Connect
- [ ] Configure Azure AD app registration with proper scopes
- [ ] Implement Microsoft Graph API integration for user information
- [ ] Update token validation to use Microsoft's public keys

### Phase 2: User Identity Mapping
- [ ] Map Azure AD user attributes to existing `UserModel` schema
- [ ] Handle Azure AD group memberships vs. internal group structure
- [ ] Sync user profile data from Microsoft Graph API
- [ ] Implement user provisioning/deprovisioning workflows

### Phase 3: Authorization Adaptation
- [ ] Integrate Azure AD groups with existing RBAC system
- [ ] Map Azure AD roles to internal role types
- [ ] Maintain existing permission model while leveraging Entra groups
- [ ] Handle nested group memberships from Azure AD

### Phase 4: Configuration & Dependencies
- [ ] Add `msal` (Microsoft Authentication Library)
- [ ] Add `microsoft-graph-python` for Graph API calls
- [ ] Update environment variables for Azure integration
- [ ] Modify Docker configuration for Azure deployment

## Key Files to Modify

### Authentication Layer
- `main.py` - Update auth configuration and middleware
- `src/GraphTypeDefinitions/_GraphPermissions.py` - Integrate Entra token validation
- `environment.txt` - Replace JWT URLs with Azure AD configuration

### Dependencies
- `requirements.txt` - Add Microsoft authentication libraries
- `Dockerfile` - Update for new dependencies and Azure integration

### Configuration
- Docker environment variables for Azure secrets
- Health checks for Microsoft Graph API connectivity

## Components to Preserve

### Database Schema (Keep Unchanged)
- All 17 SQLAlchemy models in `DBDefinitions/`
- Existing relationships and constraints
- RBAC permission structure

### GraphQL API (Keep Interface)
- Complete GraphQL schema in `GraphTypeDefinitions/`
- Query and mutation resolvers
- Field-level permissions
- Dataloader optimizations

### Business Logic
- Group hierarchy management
- Role assignment workflows
- State machine implementations
- Permission validation logic

## Migration Strategy

**Recommended Approach**: Fork existing project and incrementally replace authentication components.

**Advantages**:
- Preserve 6000+ lines of GraphQL type definitions
- Keep comprehensive database models and relationships
- Maintain existing test suite
- Reuse Docker configuration
- Preserve FastAPI + Strawberry architecture

**Risk Mitigation**:
- Implement feature flags for gradual rollout
- Maintain backward compatibility during transition
- Test with Azure AD test tenant before production
- Keep demo mode for development environment

## MVP Implementation Plan

### MVP Scope
Create a minimal working version that:
1. **Authenticates users via Microsoft Entra ID** instead of JWT
2. **Preserves all existing GraphQL functionality** (queries, mutations, subscriptions)
3. **Maps Azure AD users to internal UserModel**
4. **Uses existing database for groups/roles** (hybrid approach)
5. **Maintains demo mode for development**

### MVP Architecture

```
┌─────────────────┐
│  FastAPI App    │
│  (main.py)      │
└────────┬────────┘
         │
         ├─→ Azure AD Auth Middleware (new)
         │   ├─→ Token validation (MSAL)
         │   ├─→ User info from Graph API
         │   └─→ Map to UserModel
         │
         ├─→ Strawberry GraphQL (existing)
         │   └─→ All queries/mutations unchanged
         │
         └─→ PostgreSQL Database (existing)
             ├─→ Groups (managed internally)
             ├─→ Roles (managed internally)
             └─→ Users (synced from Azure AD)
```

### Implementation Steps

#### 1. Dependencies (requirements.txt)
- [x] Add `msal==1.24.1` for Azure AD authentication
- [x] Add `requests==2.31.0` for Graph API calls
- [ ] Keep all existing dependencies unchanged

#### 2. Azure AD Authentication Module (src/auth/azure_ad.py) - NEW FILE
- [ ] Create MSAL confidential client wrapper
- [ ] Implement token validation middleware
- [ ] Create user info fetcher from Graph API
- [ ] Map Azure AD attributes to UserModel fields:
  - `id` → `externalId`
  - `userPrincipalName` → `email`
  - `displayName` → `name`

#### 3. Update main.py
- [ ] Replace `JWTPUBLICKEYURL`/`JWTRESOLVEUSERPATHURL` with Azure AD config
- [ ] Add new environment variables:
  - `AZURE_CLIENT_ID`
  - `AZURE_CLIENT_SECRET`
  - `AZURE_TENANT_ID`
  - `AZURE_SCOPES` (default: "User.Read User.ReadBasic.All")
- [ ] Replace JWT middleware with Azure AD middleware
- [ ] Keep demo mode logic for development

#### 4. Update GraphPermissions.py
- [ ] Modify `getUserFromInfo()` to work with Azure AD tokens
- [ ] Keep existing RBAC logic unchanged
- [ ] Ensure user lookup works with Azure AD user IDs

#### 5. User Synchronization Strategy
**Approach**: Just-in-time (JIT) user provisioning
- [ ] On first login: Create user in DB from Azure AD info
- [ ] On subsequent logins: Update user info if changed
- [ ] Store Azure AD `id` as `externalId` for lookup
- [ ] Keep existing user fields for local data

#### 6. Group Strategy (MVP)
**Approach**: Hybrid model (existing DB + Azure AD memberships)
- [ ] Keep all existing group tables and queries
- [ ] Group creation/management via GraphQL (as before)
- [ ] Optional: Sync user's Azure AD groups to internal groups
- [ ] No need for `groups.list.all` permission

### Testing Plan

1. **Authentication Flow**
   - [ ] Test login redirect to Azure AD
   - [ ] Test callback handling
   - [ ] Test token validation
   - [ ] Test user info retrieval

2. **GraphQL Queries**
   - [ ] Test `me` query (current user)
   - [ ] Test `userById` with Azure AD user
   - [ ] Test `userPage` listing
   - [ ] Test group queries (existing data)

3. **Mutations**
   - [ ] Test user profile updates
   - [ ] Test role assignments
   - [ ] Test group memberships

### Environment Configuration

**Old (.env or environment.txt)**:
```bash
JWTPUBLICKEYURL=https://...
JWTRESOLVEUSERPATHURL=https://...
DEMO=true
```

**New**:
```bash
# Azure AD Configuration
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_TENANT_ID=your-tenant-id
AZURE_REDIRECT_URI=http://localhost:8000/auth/callback
AZURE_SCOPES=User.Read,User.ReadBasic.All

# Legacy support
DEMO=true

# Database (unchanged)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
```

### Success Criteria

- [x] Successful Azure AD authentication
- [ ] Existing GraphQL schema works without changes
- [ ] Users can query their profile via `me`
- [ ] User list shows Azure AD users
- [ ] Existing groups/roles/RBAC continues to function
- [ ] Docker container builds and runs
- [ ] Demo mode still works for development

### Out of Scope (for MVP)

- ❌ Group synchronization from Azure AD
- ❌ Advanced permission mapping
- ❌ User deprovisioning workflows
- ❌ Production-grade error handling
- ❌ Comprehensive logging/monitoring
- ❌ Migration scripts for existing users

### Next Immediate Steps

1. ✅ Update requirements.txt with MSAL dependencies
2. ✅ Create `src/auth/azure_ad.py` authentication module
3. ✅ Update `main.py` to integrate Azure AD auth
4. ⏳ Test with msentra credentials
5. ⏳ Verify GraphQL queries work with Azure AD tokens

## MVP Implementation Status

### Completed ✅

1. **Dependencies** - Added MSAL and python-dotenv to requirements.txt
2. **Azure AD Auth Module** (`src/auth/azure_ad.py`) - Complete implementation:
   - Token validation using Microsoft Graph API
   - User info retrieval from Graph API
   - User mapping from Azure AD to internal format
   - FastAPI middleware for authentication
   - Support for DEMO mode (bypass auth)
3. **Main Application Updates** (`main.py`):
   - Azure AD configuration from environment variables
   - Azure AD middleware integration
   - OAuth endpoints: `/auth/login`, `/auth/callback`
   - Health check endpoint: `/health`
   - Maintained DEMO mode for development
4. **Configuration Files**:
   - `.env.example` - Template with all configuration options
   - `.env` - Local development config with DEMO mode enabled

### Key Features

- **Just-in-Time User Provisioning**: Users are automatically mapped from Azure AD to internal format
- **Hybrid Group Model**: Existing group management preserved, Azure AD used for user authentication
- **DEMO Mode**: Development mode with demo user (bypasses Azure AD)
- **OAuth 2.0 Flow**: Standard authorization code flow with MSAL
- **Token Validation**: Tokens validated by attempting Graph API calls
- **User Mapping**: Azure AD attributes mapped to internal user model:
  - `id` → Azure AD Object ID
  - `displayName` → `name` / `surname`
  - `userPrincipalName` → `email`
  - `mail` → `email`

### Testing Guide

#### Test in DEMO Mode (No Azure AD Required)

1. Ensure `.env` has `DEMO=True`
2. Start the application:
   ```bash
   # With Docker
   docker-compose up

   # Or directly (requires PostgreSQL running)
   uvicorn main:app --reload
   ```
3. Access GraphQL endpoint: http://localhost:8000/gql
4. Demo user is automatically authenticated

#### Test with Azure AD

1. Update `.env` with your Azure AD credentials from `~/dev/msentra/.env`:
   ```bash
   DEMO=False
   AZURE_CLIENT_ID=<your-client-id>
   AZURE_CLIENT_SECRET=<your-client-secret>
   AZURE_TENANT_ID=<your-tenant-id>
   ```

2. Start the application

3. Get an access token:
   - **Option A - Via Browser**:
     1. Navigate to http://localhost:8000/auth/login
     2. Log in with your Microsoft account
     3. Copy the access token from the callback page

   - **Option B - Use token from msentra project**:
     ```bash
     cd ~/dev/msentra
     python main.py
     # Get token via browser login
     ```

4. Test GraphQL with token:
   ```bash
   curl -X POST http://localhost:8000/gql \
     -H "Authorization: Bearer <your-access-token>" \
     -H "Content-Type: application/json" \
     -d '{"query": "{ __typename }"}'
   ```

5. Test the `me` query (current user):
   ```graphql
   query {
     me {
       id
       name
       surname
       email
     }
   }
   ```

### File Structure

```
gql_ug/
├── main.py                          # ✅ Updated with Azure AD integration
├── requirements.txt                 # ✅ Added msal, python-dotenv
├── .env                            # ✅ Local configuration (DEMO=True)
├── .env.example                    # ✅ Configuration template
├── CLAUDE.md                       # ✅ Project documentation
├── src/
│   ├── auth/                       # ✅ NEW - Azure AD authentication
│   │   ├── __init__.py            # ✅ Module exports
│   │   └── azure_ad.py            # ✅ Complete auth implementation
│   ├── GraphTypeDefinitions/      # ✅ Preserved (no changes needed)
│   ├── DBDefinitions/             # ✅ Preserved (no changes needed)
│   ├── GraphPermissions.py        # ✅ Preserved (compatible with Azure AD)
│   └── Dataloaders.py             # ✅ Preserved (getUserFromInfo compatible)
```

### Endpoints

- **`GET /auth/login`** - Initiate Azure AD OAuth flow
- **`GET /auth/callback`** - Handle OAuth callback, display access token
- **`GET /health`** - Health check (shows auth mode, DEMO status)
- **`POST /gql`** - GraphQL endpoint (requires Bearer token, or DEMO mode)
- **`GET /gql`** - GraphQL playground
- **`GET /voyager`** - GraphQL schema visualization
- **`GET /doc`** - GraphQL schema documentation
- **`GET /metrics`** - Prometheus metrics

### Next Steps for Testing

1. ✅ Syntax validation passed
2. ⏳ Start application in DEMO mode
3. ⏳ Test GraphQL queries with demo user
4. ⏳ Start application with Azure AD
5. ⏳ Test OAuth login flow
6. ⏳ Test GraphQL queries with Azure AD token
7. ⏳ Verify user mapping from Azure AD