import os
import asyncio
import socket

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from strawberry.fastapi import GraphQLRouter


import logging
import logging.handlers

# region ENV setup - MUST be before other imports that use these values
def envAssertDefined(name, default=None):
    result = os.getenv(name, None)
    assert result is not None, f"{name} environment variable must be explicitly defined"
    return result

def envGetOptional(name, default=None):
    """Get optional environment variable"""
    return os.getenv(name, default)

# Check DEMO mode
DEMO = envAssertDefined("DEMO", None)
print(f"DEMO = {DEMO} is type {type(DEMO)}")
assert (DEMO in ["True", "true", "False", "false"]), "DEMO environment variable can have only `True` or `False` values"
DEMO = DEMO in ["True", "true"]

# Azure AD Configuration (required if not in DEMO mode)
if not DEMO:
    AZURE_CLIENT_ID = envAssertDefined("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = envAssertDefined("AZURE_CLIENT_SECRET")
    AZURE_TENANT_ID = envAssertDefined("AZURE_TENANT_ID")
    AZURE_REDIRECT_URI = envGetOptional("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    AZURE_SCOPES = envGetOptional("AZURE_SCOPES", "User.Read,User.ReadBasic.All")
else:
    # In demo mode, Azure AD config is optional
    AZURE_CLIENT_ID = envGetOptional("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = envGetOptional("AZURE_CLIENT_SECRET")
    AZURE_TENANT_ID = envGetOptional("AZURE_TENANT_ID")
    AZURE_REDIRECT_URI = envGetOptional("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    AZURE_SCOPES = envGetOptional("AZURE_SCOPES", "User.Read,User.ReadBasic.All")

# Print startup configuration
if DEMO:
    print("####################################################")
    print("#                                                  #")
    print("# RUNNING IN DEMO                                  #")
    print("#                                                  #")
    print("####################################################")
else:
    print("####################################################")
    print("#                                                  #")
    print("# RUNNING DEPLOYMENT                               #")
    print("#                                                  #")
    print("####################################################")

# endregion

from src.GraphTypeDefinitions import schema
from src.DBDefinitions import startEngine, ComposeConnectionString
from src.DBFeeder import initDB, createGroupPaths

# region logging setup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d\t%(levelname)s:\t%(message)s',
    datefmt='%Y-%m-%dT%I:%M:%S')
SYSLOGHOST = os.getenv("SYSLOGHOST", None)
if SYSLOGHOST is not None:
    [address, strport, *_] = SYSLOGHOST.split(':')
    assert len(_) == 0, f"SYSLOGHOST {SYSLOGHOST} has unexpected structure, try `localhost:514` or similar (514 is UDP port)"
    port = int(strport)
    my_logger = logging.getLogger()
    my_logger.setLevel(logging.INFO)
    handler = logging.handlers.SysLogHandler(address=(address, port), socktype=socket.SOCK_DGRAM)
    #handler = logging.handlers.SocketHandler('10.10.11.11', 611)
    my_logger.addHandler(handler)

# Log startup configuration
if DEMO:
    logging.info("####################################################")
    logging.info("#                                                  #")
    logging.info("# RUNNING IN DEMO                                  #")
    logging.info("#                                                  #")
    logging.info("####################################################")
else:
    logging.info("####################################################")
    logging.info("#                                                  #")
    logging.info("# RUNNING DEPLOYMENT                               #")
    logging.info("#                                                  #")
    logging.info("####################################################")

logging.info(f"DEMO = {DEMO}")
logging.info(f"SYSLOGHOST = {SYSLOGHOST}")
if not DEMO:
    logging.info(f"AZURE_CLIENT_ID = {AZURE_CLIENT_ID}")
    logging.info(f"AZURE_TENANT_ID = {AZURE_TENANT_ID}")
    logging.info(f"AZURE_REDIRECT_URI = {AZURE_REDIRECT_URI}")
else:
    logging.info("Azure AD authentication disabled in DEMO mode")

# endregion

# region DB setup

connectionString = ComposeConnectionString()

def singleCall(asyncFunc):
    """Dekorator, ktery dovoli, aby dekorovana funkce byla volana (vycislena) jen jednou. Navratova hodnota je zapamatovana a pri dalsich volanich vracena.
    Dekorovana funkce je asynchronni.
    """
    resultCache = {}

    async def result():
        if resultCache.get("result", None) is None:
            resultCache["result"] = await asyncFunc()
        return resultCache["result"]

    return result

@singleCall
async def RunOnceAndReturnSessionMaker():
    """Provadi inicializaci asynchronniho db engine, inicializaci databaze a vraci asynchronni SessionMaker.
    Protoze je dekorovana, volani teto funkce se provede jen jednou a vystup se zapamatuje a vraci se pri dalsich volanich.
    """

    makeDrop = os.getenv("DEMODATA", None) in ["True", "true"]
    logging.info(f'starting engine for "{connectionString} makeDrop={makeDrop}"')

    result = await startEngine(
        connectionstring=connectionString, makeDrop=makeDrop, makeUp=True
    )

    logging.info(f"initializing system structures")

    ###########################################################################################################################
    #
    # zde definujte do funkce asyncio.gather
    # vlozte asynchronni funkce, ktere maji data uvest do prvotniho konzistentniho stavu
    # await initDB(result)
    async def initAnd_(SessionMaker):
        await initDB(SessionMaker)
        await createGroupPaths(SessionMaker)
        print(f"data ready, paths created", flush=True)

    coroutine = initAnd_(result)
    asyncio.create_task(coroutine)
    
    #
    #
    ###########################################################################################################################
    logging.info(f"all done")
    return result

# endregion

# region API endpoints

from src.Dataloaders import createLoadersContext


async def get_context(request: Request):    
    result = {
        "request": request,
    }
    logging.info(f"context created {result}")
    return result

from uoishelpers.schema import SessionCommitExtensionFactory

schema.extensions.append(
    SessionCommitExtensionFactory(session_maker_factory=RunOnceAndReturnSessionMaker, loaders_factory=createLoadersContext)
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.DBFeeder import backupDB
    initizalizedEngine = await RunOnceAndReturnSessionMaker()

    # Store session maker in app state for middleware to access
    app.state.session_maker = initizalizedEngine

    yield
    await backupDB(initizalizedEngine)


app = FastAPI(lifespan=lifespan)
# app.mount("/gql", graphql_app)

# Add Azure AD authentication middleware
# Pass the session_maker_factory so middleware can access DB for JIT provisioning
from src.auth.session_middleware import SessionValidationMiddleware
app.add_middleware(SessionValidationMiddleware, demo_mode=DEMO, session_maker_factory=RunOnceAndReturnSessionMaker)
logging.info(f"Azure AD authentication middleware added (DEMO mode: {DEMO})")

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app, metric_namespace="gql_ug").expose(app, endpoint="/metrics")

graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context
)

app.include_router(graphql_app, prefix="/gql")

@app.get("/voyager", response_class=FileResponse)
async def graphiql():
    realpath = os.path.realpath("./src/Htmls/voyager.html")
    return realpath

@app.get("/doc", response_class=FileResponse)
async def graphiql():
    realpath = os.path.realpath("./src/Htmls/liveschema.html")
    return realpath

@app.get("/ui", response_class=FileResponse)
async def graphiql():
    realpath = os.path.realpath("./src/Htmls/livedata.html")
    return realpath

@app.get("/test", response_class=FileResponse)
async def graphiql():
    realpath = os.path.realpath("./src/Htmls/tests.html")
    return realpath

# ============================================================================
# NOTE: Azure AD OAuth endpoints have been moved to frontendui
# The frontendui service now handles authentication at /auth/login, /auth/callback, /auth/logout
# This service (gql_ug) now only validates sessions via SessionValidationMiddleware
# OAuth endpoints below are commented out for reference
# ============================================================================

# # Azure AD OAuth endpoints (DISABLED - now handled by frontendui)
# # from fastapi.responses import RedirectResponse, HTMLResponse
# # from src.auth.azure_ad import (
# #     get_msal_app,
# #     get_azure_config,
# #     create_pkce_params,
# #     store_pkce_verifier,
# #     get_pkce_verifier,
# #     store_access_token,
# #     clear_access_token
# # )
# # import uuid
#
# # @app.get("/auth/login")
# # async def azure_login(request: Request):
# #     """Initiate Azure AD OAuth flow with PKCE"""
# #     ... (implementation removed - now in frontendui)
#
# # @app.get("/auth/callback")
# # async def azure_callback(code: str = None, state: str = None, error: str = None, error_description: str = None):
# #     """Handle Azure AD OAuth callback with PKCE"""
# #     ... (implementation removed - now in frontendui)
#
# # @app.get("/auth/logout")
# # async def azure_logout(request: Request):
# #     """Logout endpoint - clears session"""
# #     ... (implementation removed - now in frontendui)
#
# # End of commented out OAuth endpoints - all auth now handled by frontendui

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "demo_mode": DEMO,
        "authentication": "azure_ad" if not DEMO else "demo"
    }

logging.info("All initialization is done")

# from src.router.router import create_router_from_schema
# router = create_router_from_schema(schema)
# app.include_router(router, prefix="/ui")
# endregion