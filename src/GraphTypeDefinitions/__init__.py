import typing
from typing import List, Union, Optional
import strawberry
import uuid
import datetime
import graphql
import logging

# from contextlib import asynccontextmanager


# @asynccontextmanager
# async def withInfo(info):
#     asyncSessionMaker = info.context["asyncSessionMaker"]
#     async with asyncSessionMaker() as session:
#         try:
#             yield session
#         finally:
#             pass


# def getLoader(info):
#     return info.context["all"]


import datetime
    
###########################################################################################################################
#
# Schema je pouzito v main.py, vsimnete si parametru types, obsahuje vyjmenovane modely. Bez explicitniho vyjmenovani
# se ve schema objevi jen ty struktury, ktere si strawberry dokaze odvodit z Query. Protoze v teto konkretni implementaci
# nektere modely nejsou s Query propojene je potreba je explicitne vyjmenovat. Jinak ve federativnim schematu nebude
# dostupne rozsireni, ktere tento prvek federace implementuje.
#
###########################################################################################################################

from .query import Query
from .mutation import Mutation

from .userGQLModel import UserGQLModel # jen jako demo
from .groupGQLModel import GroupGQLModel
from .groupTypeGQLModel import GroupTypeGQLModel
from .membershipGQLModel import MembershipGQLModel
from .roleGQLModel import RoleGQLModel
# from .deprecated.roleCategoryGQLModel import RoleCategoryGQLModel
from .roleTypeGQLModel import RoleTypeGQLModel

from .RBACObjectGQLModel import RBACObjectGQLModel, RBACStateObjectGQLModel
from .BaseGQLModel import IDType, Relation


from strawberry.extensions import SchemaExtension
from starlette.requests import Request
# import inspect
import aiohttp
import os

from uoishelpers.schema import WhoAmIExtension
from uoishelpers.gqlpermissions.ApplyPermissionCheckRoleDirectiveMixin import PermissionCheckRoleDirective

schema = strawberry.federation.Schema(
    query=Query, 
    types=(RBACObjectGQLModel, RBACStateObjectGQLModel, IDType), 
    mutation=Mutation, 
    extensions=[],
    schema_directives=[Relation, PermissionCheckRoleDirective]
)

readonlyschema = strawberry.federation.Schema(query=Query, types=(RBACObjectGQLModel, IDType))

# region Sentinel setup
JWTPUBLICKEYURL = os.environ.get("JWTPUBLICKEYURL", "http://localhost:8000/oauth/publickey")
JWTRESOLVEUSERPATHURL = os.environ.get("JWTRESOLVEUSERPATHURL", "http://localhost:8000/oauth/userinfo")

apolloQuery = "query __ApolloGetServiceDefinition__ { _service { sdl } }"
graphiQLQuery = "\n    query IntrospectionQuery {\n      __schema {\n        \n        queryType { name }\n        mutationType { name }\n        subscriptionType { name }\n        types {\n          ...FullType\n        }\n        directives {\n          name\n          description\n          \n          locations\n          args(includeDeprecated: true) {\n            ...InputValue\n          }\n        }\n      }\n    }\n\n    fragment FullType on __Type {\n      kind\n      name\n      description\n      \n      fields(includeDeprecated: true) {\n        name\n        description\n        args(includeDeprecated: true) {\n          ...InputValue\n        }\n        type {\n          ...TypeRef\n        }\n        isDeprecated\n        deprecationReason\n      }\n      inputFields(includeDeprecated: true) {\n        ...InputValue\n      }\n      interfaces {\n        ...TypeRef\n      }\n      enumValues(includeDeprecated: true) {\n        name\n        description\n        isDeprecated\n        deprecationReason\n      }\n      possibleTypes {\n        ...TypeRef\n      }\n    }\n\n    fragment InputValue on __InputValue {\n      name\n      description\n      type { ...TypeRef }\n      defaultValue\n      isDeprecated\n      deprecationReason\n    }\n\n    fragment TypeRef on __Type {\n      kind\n      name\n      ofType {\n        kind\n        name\n        ofType {\n          kind\n          name\n          ofType {\n            kind\n            name\n            ofType {\n              kind\n              name\n              ofType {\n                kind\n                name\n                ofType {\n                  kind\n                  name\n                  ofType {\n                    kind\n                    name\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n    }\n  "
roleTypeQuery = """query($limit: Int) {roleTypePage(limit: $limit) {id, name, nameEn}}"""
q1 = "query{__schema{types{name}}}"
q2 = "query IntrospectionQuery{__schema{queryType{name kind}mutationType{name kind}subscriptionType{name kind}types{...FullType}directives{name description locations args{...InputValue}}}}fragment FullType on __Type{kind name description fields(includeDeprecated:true){name description args{...InputValue}type{...TypeRef}isDeprecated deprecationReason}inputFields{...InputValue}interfaces{...TypeRef}enumValues(includeDeprecated:true){name description isDeprecated deprecationReason}possibleTypes{...TypeRef}}fragment InputValue on __InputValue{name description type{...TypeRef}defaultValue}fragment TypeRef on __Type{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name}}}}}}}}}}"

from uoishelpers.authenticationMiddleware import createAuthentizationSentinel
from fastapi.responses import JSONResponse

sentinel = createAuthentizationSentinel(
    JWTPUBLICKEY=JWTPUBLICKEYURL,
    JWTRESOLVEUSERPATH=JWTRESOLVEUSERPATHURL,
    queriesWOAuthentization=[apolloQuery, graphiQLQuery, roleTypeQuery, q1, q2],
    onAuthenticationError=lambda item: JSONResponse({"data": None, "errors": ["Unauthenticated", item.query, f"{item.variables}"]}, 
    status_code=401))

# endregion

from uoishelpers.authenticationMiddleware import createAuthentizationSentinel
from pydantic import BaseModel

class Item(BaseModel):
    query: str
    variables: dict = {}
    operationName: str = None


me_query = """{
  me {
    id
    fullname
    email
    roles(where: {valid: {_eq: true}}, limit: 1000) {
      valid
      group { id name }
      roletype { id name }
    }
  }
}"""
class UGWhoAmIExtension(WhoAmIExtension):
    def __init__(self, execution_context):
        self.logger = logging.getLogger(__name__)
        JWTPUBLICKEYURL = os.environ.get("JWTPUBLICKEYURL", "http://localhost:8000/oauth/publickey")
        JWTRESOLVEUSERPATHURL = os.environ.get("JWTRESOLVEUSERPATHURL", "http://localhost:8000/oauth/userinfo")
        self.sentinel = createAuthentizationSentinel(
            queriesWOAuthentization=[],
            JWTPUBLICKEY=JWTPUBLICKEYURL,
            JWTRESOLVEUSERPATH=JWTRESOLVEUSERPATHURL,
            onAuthenticationError=lambda item: JSONResponse({"data": None, "errors": ["Unauthenticated", item.query, f"{item.variables}"]},
                status_code=401)
        )

    async def ug_query(self, query, variables={}, is_UGWhoAmIExtension=False):
        await self.authorize()
        context = self.execution_context.context
        # print(f"ug_query context A = {context}")
        # result = await self.execution_context.schema.execute(query=query, variable_values=variables, context_value=context)
        if is_UGWhoAmIExtension:
            print(f"is_UGWhoAmIExtension")
        else:
            print(f"not is_UGWhoAmIExtension")
        print(f"query for gql_ug with \n{query}\nvariables\n{variables}")
        result = await readonlyschema.execute(query=query, variable_values=variables, context_value=context)
        # print(f"ug_query context B = {context}")
        result = strawberry.asdict(result)
        # print(f"result = {result}")
        return result

    async def authorize(self):
        user = self.execution_context.context.get("user")
        if user is not None:
            return
        request = self.execution_context.context.get("request")

        # Check if SessionValidationMiddleware already set complete Azure AD user data
        existing_user = request.scope.get("user", None)
        if (existing_user and
            existing_user.get("source") == "azure_ad" and
            existing_user.get("name") and
            existing_user.get("surname")):
            # User already authenticated by SessionValidationMiddleware with DB UUID
            # Skip Sentinel validation to preserve the correct user data
            self.logger.info(f"Using authenticated Azure AD user from SessionValidationMiddleware: {existing_user.get('email')}")
            return

        # Call Sentinel for DEMO mode, legacy JWT auth, or when SessionValidationMiddleware didn't run
        item = Item(variables={}, query="")
        await self.sentinel(request, item)

    async def on_execute(self):
        # print(f"UGWhoAmIExtension")
        from graphql import print_ast
        query_sdl = "{\n  _service {\n    sdl\n  }\n}"        
        queries = [
            query_sdl,
            "{\n  __schema {\n    types {\n      name\n    }\n  }\n}",
            "query __ApolloGetServiceDefinition__ {\n  _service {\n    sdl\n  }\n}",
            """query __ApolloGetServiceDefinition__ {
  _service {
    sdl
  }
}"""
        ]
        
        # print(f"printed attrs: {dir(self.execution_context)}", flush=True)
        graphql_document = self.execution_context.graphql_document
        query_str = print_ast(graphql_document)
        to_pass = query_str in queries
        # print(f"printed query ast: {query_str} {to_pass}", flush=True)
        context = self.execution_context
        context.context["ug_client"] = self.ug_query
        # print(f"ug_client is set in context {self.ug_query}")
        context.context["query_str"] = query_str
        if not to_pass:
            whoami = await self.ug_query(query=me_query, is_UGWhoAmIExtension=True)
            # data = whoami.get("data", {"me": {"roles": []}})
            data = whoami.get("data", None)
            if data is None:        
                raise graphql.GraphQLError(
                    "UGWhoAmIExtension: Unauthenticated",
                    extensions={
                        "code": "dc7c8f84-c726-43dc-a99b-f373942326cd", 
                        "details": "You are not logged in"
                    }
                )        
            user = data.get("me", None)
            if user is None:
                raise graphql.GraphQLError(
                    "UGWhoAmIExtension: Unauthenticated",
                    extensions={
                        "code": "dc7c8f84-c726-43dc-a99b-f373942326cd", 
                        "details": "You are not logged in"
                    }
                )
            # print(f"UGWhoAmIExtension:user={user}")
            context.context["user"] = user
            
        # print(f"UGWhoAmIExtension.on_execute {data}:{user}")
        # print(f"UGWhoAmIExtension.on_execute {user}")
        # print(f"""UGWhoAmIExtension.on_execute {self.execution_context.context["user"]}""")

        # print(f"user\n{user}\nquery\n{context.query}\nvariables\n{context.variables}")
        # print(f"UGWhoAmIExtension.on_execute started for {user}", flush=True)
        yield
        # print(f"UGWhoAmIExtension.on_execute ended", flush=True)
    
from uoishelpers.schema import PrometheusExtension, ProfilingExtension
if os.getenv("DEMO", None) in ["True", "true", True]:
    print("ProfilingExtension is enabled")
    schema.extensions.append(ProfilingExtension)

schema.extensions.extend([PrometheusExtension(prefix="prom"), UGWhoAmIExtension])

from uoishelpers.gqlpermissions.RolePermissionSchemaExtension import RolePermissionSchemaExtension, GraphQLBatchLoader
schema.extensions.append(RolePermissionSchemaExtension)

from strawberry.extensions import ParserCache, ValidationCache

schema.extensions.append(ParserCache(1000))
schema.extensions.append(ValidationCache(1000))
print(f"schema.extensions.length: {len(schema.extensions)}")