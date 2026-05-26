"""ShopifyPlugin — full Shopify Admin API integration for tbd-agents.

Provides read and write access to the Shopify Admin GraphQL API (v2024-10),
covering products, variants, orders, customers, inventory, draft orders,
discount codes, refunds, fulfillments, and cancellations.

Required configuration
----------------------
``SHOPIFY_SHOP_DOMAIN``
    Your myshopify.com domain, e.g. ``mystore.myshopify.com``.
    Falls back to the ``shop_domain`` argument on each call.

``SHOPIFY_ADMIN_API_TOKEN``
    A private-app or custom-app Admin API access token with the scopes
    required for your operations:

    - ``read_products`` / ``write_products``
    - ``read_orders`` / ``write_orders``
    - ``read_customers`` / ``write_customers``
    - ``read_inventory`` / ``write_inventory``
    - ``read_draft_orders`` / ``write_draft_orders``
    - ``read_discounts`` / ``write_discounts``
    - ``read_fulfillments`` / ``write_fulfillments``

``SHOPIFY_API_VERSION``
    Defaults to ``2024-10``.  Override in env to pin a different version.

Safety model
------------
* Destructive operations (``refund_order``, ``cancel_order``) require a
  non-empty ``approval_token``.  The plugin validates this and returns an
  error if the token is absent; enforcement of *what* constitutes a valid
  token is handled by the agent's guardrails layer, not this plugin.
* Bulk-style writes default to ``dry_run=True``, returning a preview dict
  without calling the API.
* An ``Idempotency-Key`` header is sent with all write mutations to prevent
  accidental duplicate processing on retries.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_API_VERSION = "2024-10"
_MAX_LIMIT = 250  # Shopify hard cap per page

_READ_OPS = {
    "list_products",
    "get_product",
    "list_orders",
    "get_order",
    "list_customers",
    "get_customer",
    "list_inventory_levels",
    "list_locations",
    "list_draft_orders",
    "list_discounts",
}

_WRITE_OPS = {
    "update_product",
    "update_variant_price",
    "update_inventory_level",
    "tag_customer",
    "create_draft_order",
    "create_discount_code",
    "refund_order",
    "fulfill_order",
    "cancel_order",
}

_DESTRUCTIVE_OPS = {"refund_order", "cancel_order"}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class ShopifyPlugin(PluginBase):
    """Shopify Admin API plugin for read and write store operations.

    Covers the full operational surface needed by the Shopify Ops Agent:
    product catalog management, variant pricing, inventory adjustments,
    customer tagging, draft order creation, discount code generation,
    order refunds, fulfillment, and order cancellation.

    Read operations
    ---------------
    ``list_products``
        List products with optional keyword filter and pagination.
    ``get_product``
        Fetch a single product by its global ID.
    ``list_orders``
        List orders; filter by ``status`` (``open`` / ``closed`` / ``any``).
    ``get_order``
        Fetch full details for a single order.
    ``list_customers``
        List customers with optional query filter.
    ``get_customer``
        Fetch a customer by global ID.
    ``list_inventory_levels``
        List inventory levels for a specific location.
    ``list_locations``
        List all fulfillment locations in the store.
    ``list_draft_orders``
        List draft orders; filter by ``status`` (``open`` / ``completed``).
    ``list_discounts``
        List discount nodes (automatic + code discounts).

    Write operations
    ----------------
    ``update_product``
        Update product fields (title, body_html, vendor, tags, status, etc.)
        via ``productUpdate`` mutation.
    ``update_variant_price``
        Set a new ``price`` on a specific product variant.
    ``update_inventory_level``
        Adjust available quantity at a location via ``inventorySetQuantities``.
    ``tag_customer``
        Append tags to an existing customer record.
    ``create_draft_order``
        Create a draft order from a line-items payload.
    ``create_discount_code``
        Create a basic discount code (percentage or fixed-amount).
    ``refund_order``
        Issue a refund on an order.  **Requires** a non-empty
        ``approval_token``; returns ``{"error": "..."}`` when absent.
    ``fulfill_order``
        Mark an order fulfillment as fulfilled via ``fulfillmentCreate``.
    ``cancel_order``
        Cancel an open order.  **Requires** a non-empty ``approval_token``.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "shopify"

    @property
    def description(self) -> str:
        return (
            "Shopify Admin API integration for e-commerce store operations. "
            "Read operations: list_products (browse catalog with filters), "
            "get_product (single product details), list_orders (all orders with "
            "status filter), get_order (full order details), list_customers "
            "(customer directory), get_customer (single customer), "
            "list_inventory_levels (stock at a location), list_locations (all "
            "fulfillment locations), list_draft_orders (open/completed drafts), "
            "list_discounts (active discounts). "
            "Write operations: update_product (edit product fields), "
            "update_variant_price (change SKU price), update_inventory_level "
            "(adjust stock quantity), tag_customer (apply tags to a customer), "
            "create_draft_order (build a new draft order from line items), "
            "create_discount_code (generate a percentage or fixed-amount code), "
            "refund_order (issue a refund — requires approval_token), "
            "fulfill_order (mark fulfillment complete), "
            "cancel_order (cancel an open order — requires approval_token). "
            "All write calls include an Idempotency-Key header. "
            "Bulk writes support dry_run=True to preview changes without "
            "calling the API. Uses Shopify Admin GraphQL API version 2024-10."
        )

    @property
    def tags(self) -> list[str]:
        return ["shopify", "ecommerce", "ops", "catalog", "orders", "inventory", "read", "write"]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "SHOPIFY_SHOP_DOMAIN": "{{token:shopify-shop-domain}}",
            "SHOPIFY_ADMIN_API_TOKEN": "{{token:shopify-admin-api-token}}",
            "SHOPIFY_API_VERSION": "2024-10",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_endpoint(self, shop_domain: str) -> str:
        """Build the Admin GraphQL endpoint URL.

        Args:
            shop_domain: myshopify.com domain (e.g. ``mystore.myshopify.com``).
                Falls back to ``SHOPIFY_SHOP_DOMAIN`` env var if empty.

        Returns:
            Full HTTPS endpoint string.

        Raises:
            ValueError: If no shop domain can be resolved.
        """
        domain = shop_domain.strip() or os.environ.get("SHOPIFY_SHOP_DOMAIN", "").strip()
        if not domain:
            raise ValueError(
                "shop_domain is required. Pass it as an argument or set "
                "SHOPIFY_SHOP_DOMAIN in the environment."
            )
        version = os.environ.get("SHOPIFY_API_VERSION", _DEFAULT_API_VERSION).strip()
        return f"https://{domain}/admin/api/{version}/graphql.json"

    def _get_token(self) -> str:
        """Retrieve the Admin API token from the environment.

        Returns:
            The token string.

        Raises:
            ValueError: If ``SHOPIFY_ADMIN_API_TOKEN`` is not set.
        """
        token = os.environ.get("SHOPIFY_ADMIN_API_TOKEN", "").strip()
        if not token:
            raise ValueError("SHOPIFY_ADMIN_API_TOKEN is not set in the environment.")
        return token

    def _gql(
        self,
        shop_domain: str,
        query: str,
        variables: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Execute a GraphQL request against the Shopify Admin API.

        Args:
            shop_domain: Shopify shop domain; passed to :meth:`_get_endpoint`.
            query: GraphQL query or mutation string.
            variables: Optional variables dict.
            idempotency_key: When provided, sent as ``Idempotency-Key`` header.

        Returns:
            The parsed JSON response dict, or ``{"error": "..."}`` on failure.
        """
        import requests  # noqa: PLC0415

        try:
            endpoint = self._get_endpoint(shop_domain)
            token = self._get_token()
        except ValueError as exc:
            return {"error": str(exc)}

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            return {"error": f"HTTP {exc.response.status_code}: {exc.response.text}"}
        except requests.exceptions.RequestException as exc:
            return {"error": f"Request failed: {exc}"}

        data = response.json()
        if "errors" in data:
            return {"error": data["errors"]}
        return data.get("data", data)

    @staticmethod
    def _idempotency_key() -> str:
        """Generate a new UUID4 idempotency key."""
        return str(uuid.uuid4())

    @staticmethod
    def _gid(resource: str, raw_id: str) -> str:
        """Ensure *raw_id* is a Shopify Global ID (GID).

        If the ID already starts with ``gid://``, it is returned as-is.
        Otherwise it is wrapped: ``gid://shopify/{resource}/{raw_id}``.

        Args:
            resource: Shopify resource type, e.g. ``"Product"``.
            raw_id: Numeric or GID string.

        Returns:
            A valid GID string.
        """
        raw_id = raw_id.strip()
        if raw_id.startswith("gid://"):
            return raw_id
        return f"gid://shopify/{resource}/{raw_id}"

    # ------------------------------------------------------------------
    # Read handlers
    # ------------------------------------------------------------------

    def _list_products(
        self, shop_domain: str, query_filter: str, limit: int, cursor: str
    ) -> dict:
        """List products from the store catalog."""
        gql = """
        query ListProducts($first: Int!, $after: String, $query: String) {
          products(first: $first, after: $after, query: $query) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id title handle status vendor
                variants(first: 10) {
                  edges {
                    node { id sku price inventoryQuantity }
                  }
                }
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, _MAX_LIMIT)}
        if cursor:
            variables["after"] = cursor
        if query_filter:
            variables["query"] = query_filter

        result = self._gql(shop_domain, gql, variables)
        if "error" in result:
            return result

        products_data = result.get("products", {})
        products = [
            {
                "id": e["node"]["id"],
                "title": e["node"]["title"],
                "handle": e["node"]["handle"],
                "status": e["node"]["status"],
                "vendor": e["node"]["vendor"],
                "variants": [
                    {
                        "id": v["node"]["id"],
                        "sku": v["node"]["sku"],
                        "price": v["node"]["price"],
                        "inventory_quantity": v["node"]["inventoryQuantity"],
                    }
                    for v in e["node"]["variants"]["edges"]
                ],
            }
            for e in products_data.get("edges", [])
        ]
        page_info = products_data.get("pageInfo", {})
        return {
            "products": products,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor", ""),
        }

    def _get_product(self, shop_domain: str, product_id: str) -> dict:
        """Fetch a single product by global ID."""
        if not product_id:
            return {"error": "product_id is required for get_product."}

        gql = """
        query GetProduct($id: ID!) {
          product(id: $id) {
            id title handle status descriptionHtml vendor productType tags
            createdAt updatedAt
            variants(first: 100) {
              edges {
                node {
                  id title sku price compareAtPrice
                  inventoryQuantity barcode
                  selectedOptions { name value }
                }
              }
            }
            images(first: 10) {
              edges { node { id url altText } }
            }
          }
        }
        """
        result = self._gql(shop_domain, gql, {"id": self._gid("Product", product_id)})
        if "error" in result:
            return result

        product = result.get("product")
        if not product:
            return {"error": f"Product not found: {product_id}"}

        return {
            "product": {
                "id": product["id"],
                "title": product["title"],
                "handle": product["handle"],
                "status": product["status"],
                "description_html": product.get("descriptionHtml", ""),
                "vendor": product.get("vendor", ""),
                "product_type": product.get("productType", ""),
                "tags": product.get("tags", []),
                "created_at": product.get("createdAt", ""),
                "updated_at": product.get("updatedAt", ""),
                "variants": [
                    {
                        "id": v["node"]["id"],
                        "title": v["node"]["title"],
                        "sku": v["node"]["sku"],
                        "price": v["node"]["price"],
                        "compare_at_price": v["node"].get("compareAtPrice"),
                        "inventory_quantity": v["node"]["inventoryQuantity"],
                        "barcode": v["node"].get("barcode", ""),
                        "options": v["node"].get("selectedOptions", []),
                    }
                    for v in product["variants"]["edges"]
                ],
                "images": [
                    {"id": img["node"]["id"], "url": img["node"]["url"], "alt_text": img["node"].get("altText", "")}
                    for img in product.get("images", {}).get("edges", [])
                ],
            }
        }

    def _list_orders(
        self, shop_domain: str, status: str, query_filter: str, limit: int, cursor: str
    ) -> dict:
        """List orders with optional status and query filter."""
        q_parts = []
        if status:
            q_parts.append(f"status:{status}")
        if query_filter:
            q_parts.append(query_filter)
        combined_query = " ".join(q_parts) or None

        gql = """
        query ListOrders($first: Int!, $after: String, $query: String) {
          orders(first: $first, after: $after, query: $query) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id name email createdAt displayFinancialStatus
                displayFulfillmentStatus totalPriceSet { shopMoney { amount currencyCode } }
                customer { id email firstName lastName }
                lineItems(first: 10) {
                  edges { node { title quantity sku } }
                }
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, _MAX_LIMIT)}
        if cursor:
            variables["after"] = cursor
        if combined_query:
            variables["query"] = combined_query

        result = self._gql(shop_domain, gql, variables)
        if "error" in result:
            return result

        orders_data = result.get("orders", {})
        orders = [
            {
                "id": e["node"]["id"],
                "name": e["node"]["name"],
                "email": e["node"].get("email", ""),
                "created_at": e["node"]["createdAt"],
                "financial_status": e["node"]["displayFinancialStatus"],
                "fulfillment_status": e["node"]["displayFulfillmentStatus"],
                "total_price": e["node"]["totalPriceSet"]["shopMoney"]["amount"],
                "currency": e["node"]["totalPriceSet"]["shopMoney"]["currencyCode"],
                "customer": e["node"].get("customer"),
                "line_items": [
                    {"title": li["node"]["title"], "quantity": li["node"]["quantity"], "sku": li["node"].get("sku", "")}
                    for li in e["node"]["lineItems"]["edges"]
                ],
            }
            for e in orders_data.get("edges", [])
        ]
        page_info = orders_data.get("pageInfo", {})
        return {
            "orders": orders,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor", ""),
        }

    def _get_order(self, shop_domain: str, order_id: str) -> dict:
        """Fetch full details for a single order."""
        if not order_id:
            return {"error": "order_id is required for get_order."}

        gql = """
        query GetOrder($id: ID!) {
          order(id: $id) {
            id name email phone createdAt updatedAt
            displayFinancialStatus displayFulfillmentStatus cancelledAt cancelReason
            totalPriceSet { shopMoney { amount currencyCode } }
            subtotalPriceSet { shopMoney { amount currencyCode } }
            totalTaxSet { shopMoney { amount currencyCode } }
            totalShippingPriceSet { shopMoney { amount currencyCode } }
            refunds(first: 5) { id note totalRefundedSet { shopMoney { amount currencyCode } } }
            customer { id email firstName lastName }
            shippingAddress { address1 address2 city province country zip }
            lineItems(first: 50) {
              edges {
                node {
                  id title quantity sku originalUnitPriceSet { shopMoney { amount currencyCode } }
                  variant { id sku }
                }
              }
            }
            fulfillments {
              id status trackingInfo { number url company }
            }
            tags
            note
          }
        }
        """
        result = self._gql(shop_domain, gql, {"id": self._gid("Order", order_id)})
        if "error" in result:
            return result

        order = result.get("order")
        if not order:
            return {"error": f"Order not found: {order_id}"}
        return {"order": order}

    def _list_customers(
        self, shop_domain: str, query_filter: str, limit: int, cursor: str
    ) -> dict:
        """List customers with optional query filter."""
        gql = """
        query ListCustomers($first: Int!, $after: String, $query: String) {
          customers(first: $first, after: $after, query: $query) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id email firstName lastName phone
                ordersCount totalSpentV2 { amount currencyCode }
                tags createdAt
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, _MAX_LIMIT)}
        if cursor:
            variables["after"] = cursor
        if query_filter:
            variables["query"] = query_filter

        result = self._gql(shop_domain, gql, variables)
        if "error" in result:
            return result

        customers_data = result.get("customers", {})
        customers = [
            {
                "id": e["node"]["id"],
                "email": e["node"].get("email", ""),
                "first_name": e["node"].get("firstName", ""),
                "last_name": e["node"].get("lastName", ""),
                "phone": e["node"].get("phone", ""),
                "orders_count": e["node"].get("ordersCount", 0),
                "total_spent": e["node"]["totalSpentV2"]["amount"],
                "currency": e["node"]["totalSpentV2"]["currencyCode"],
                "tags": e["node"].get("tags", []),
                "created_at": e["node"]["createdAt"],
            }
            for e in customers_data.get("edges", [])
        ]
        page_info = customers_data.get("pageInfo", {})
        return {
            "customers": customers,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor", ""),
        }

    def _get_customer(self, shop_domain: str, customer_id: str) -> dict:
        """Fetch a customer by global ID."""
        if not customer_id:
            return {"error": "customer_id is required for get_customer."}

        gql = """
        query GetCustomer($id: ID!) {
          customer(id: $id) {
            id email firstName lastName phone
            ordersCount totalSpentV2 { amount currencyCode }
            tags addresses { address1 city country zip }
            note createdAt updatedAt
            orders(first: 5) {
              edges { node { id name createdAt displayFinancialStatus } }
            }
          }
        }
        """
        result = self._gql(shop_domain, gql, {"id": self._gid("Customer", customer_id)})
        if "error" in result:
            return result

        customer = result.get("customer")
        if not customer:
            return {"error": f"Customer not found: {customer_id}"}
        return {"customer": customer}

    def _list_inventory_levels(
        self, shop_domain: str, location_id: str, limit: int, cursor: str
    ) -> dict:
        """List inventory levels at a specific location."""
        if not location_id:
            return {"error": "location_id is required for list_inventory_levels."}

        gql = """
        query ListInventoryLevels($locationId: ID!, $first: Int!, $after: String) {
          location(id: $locationId) {
            id name
            inventoryLevels(first: $first, after: $after) {
              pageInfo { hasNextPage endCursor }
              edges {
                node {
                  id quantities(names: ["available", "on_hand"]) { name quantity }
                  item { id sku variant { id product { id title } } }
                }
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {
            "locationId": self._gid("Location", location_id),
            "first": min(limit, _MAX_LIMIT),
        }
        if cursor:
            variables["after"] = cursor

        result = self._gql(shop_domain, gql, variables)
        if "error" in result:
            return result

        location = result.get("location")
        if not location:
            return {"error": f"Location not found: {location_id}"}

        levels_data = location.get("inventoryLevels", {})
        levels = [
            {
                "id": e["node"]["id"],
                "quantities": {q["name"]: q["quantity"] for q in e["node"].get("quantities", [])},
                "item_id": e["node"]["item"]["id"],
                "sku": e["node"]["item"].get("sku", ""),
                "variant_id": e["node"]["item"].get("variant", {}).get("id", ""),
                "product_id": e["node"]["item"].get("variant", {}).get("product", {}).get("id", ""),
                "product_title": e["node"]["item"].get("variant", {}).get("product", {}).get("title", ""),
            }
            for e in levels_data.get("edges", [])
        ]
        page_info = levels_data.get("pageInfo", {})
        return {
            "location_id": location["id"],
            "location_name": location["name"],
            "inventory_levels": levels,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor", ""),
        }

    def _list_locations(self, shop_domain: str, limit: int) -> dict:
        """List all active fulfillment locations."""
        gql = """
        query ListLocations($first: Int!) {
          locations(first: $first, includeInactive: false) {
            edges {
              node {
                id name isActive fulfillsOnlineOrders
                address { address1 address2 city province country zip }
              }
            }
          }
        }
        """
        result = self._gql(shop_domain, gql, {"first": min(limit, _MAX_LIMIT)})
        if "error" in result:
            return result

        locations = [
            {
                "id": e["node"]["id"],
                "name": e["node"]["name"],
                "is_active": e["node"]["isActive"],
                "fulfills_online": e["node"]["fulfillsOnlineOrders"],
                "address": e["node"].get("address", {}),
            }
            for e in result.get("locations", {}).get("edges", [])
        ]
        return {"locations": locations}

    def _list_draft_orders(
        self, shop_domain: str, status: str, limit: int, cursor: str
    ) -> dict:
        """List draft orders with optional status filter."""
        q_filter = f"status:{status}" if status else None

        gql = """
        query ListDraftOrders($first: Int!, $after: String, $query: String) {
          draftOrders(first: $first, after: $after, query: $query) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id name status email createdAt updatedAt
                totalPriceSet { shopMoney { amount currencyCode } }
                customer { id email firstName lastName }
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, _MAX_LIMIT)}
        if cursor:
            variables["after"] = cursor
        if q_filter:
            variables["query"] = q_filter

        result = self._gql(shop_domain, gql, variables)
        if "error" in result:
            return result

        drafts_data = result.get("draftOrders", {})
        drafts = [
            {
                "id": e["node"]["id"],
                "name": e["node"]["name"],
                "status": e["node"]["status"],
                "email": e["node"].get("email", ""),
                "created_at": e["node"]["createdAt"],
                "updated_at": e["node"]["updatedAt"],
                "total_price": e["node"]["totalPriceSet"]["shopMoney"]["amount"],
                "currency": e["node"]["totalPriceSet"]["shopMoney"]["currencyCode"],
                "customer": e["node"].get("customer"),
            }
            for e in drafts_data.get("edges", [])
        ]
        page_info = drafts_data.get("pageInfo", {})
        return {
            "draft_orders": drafts,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor", ""),
        }

    def _list_discounts(self, shop_domain: str, limit: int, cursor: str) -> dict:
        """List discount nodes (automatic + code discounts)."""
        gql = """
        query ListDiscounts($first: Int!, $after: String) {
          discountNodes(first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id
                discount {
                  ... on DiscountCodeBasic {
                    title status startsAt endsAt usageLimit
                    codes(first: 5) { edges { node { code } } }
                  }
                  ... on DiscountAutomaticBasic {
                    title status startsAt endsAt
                  }
                  ... on DiscountCodeBxgy {
                    title status startsAt endsAt
                  }
                  ... on DiscountAutomaticBxgy {
                    title status startsAt endsAt
                  }
                }
              }
            }
          }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, _MAX_LIMIT)}
        if cursor:
            variables["after"] = cursor

        result = self._gql(shop_domain, gql, variables)
        if "error" in result:
            return result

        nodes_data = result.get("discountNodes", {})
        discounts = [
            {"id": e["node"]["id"], "discount": e["node"].get("discount", {})}
            for e in nodes_data.get("edges", [])
        ]
        page_info = nodes_data.get("pageInfo", {})
        return {
            "discounts": discounts,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor", ""),
        }

    # ------------------------------------------------------------------
    # Write handlers
    # ------------------------------------------------------------------

    def _update_product(
        self, shop_domain: str, product_id: str, payload: dict, dry_run: bool
    ) -> dict:
        """Update product fields via ``productUpdate`` mutation."""
        if not product_id:
            return {"error": "product_id is required for update_product."}
        if not payload:
            return {"error": "payload is required for update_product (e.g. {title: 'New Title'})."}

        gid = self._gid("Product", product_id)

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {"productUpdate": {"product": {"id": gid, **payload}}},
                "items_affected": 1,
            }

        gql = """
        mutation UpdateProduct($input: ProductInput!) {
          productUpdate(input: $input) {
            product {
              id title handle status updatedAt
            }
            userErrors { field message }
          }
        }
        """
        variables = {"input": {"id": gid, **payload}}
        result = self._gql(shop_domain, gql, variables, idempotency_key=self._idempotency_key())
        if "error" in result:
            return result

        mutation_result = result.get("productUpdate", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {"product": mutation_result.get("product", {}), "user_errors": []}

    def _update_variant_price(
        self, shop_domain: str, variant_id: str, price: str, dry_run: bool
    ) -> dict:
        """Set a new price on a product variant."""
        if not variant_id:
            return {"error": "variant_id is required for update_variant_price."}
        if not price:
            return {"error": "price is required for update_variant_price (e.g. '29.99')."}

        gid = self._gid("ProductVariant", variant_id)

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {"productVariantUpdate": {"variant": {"id": gid, "price": price}}},
                "items_affected": 1,
            }

        gql = """
        mutation UpdateVariantPrice($input: ProductVariantInput!) {
          productVariantUpdate(input: $input) {
            productVariant { id price sku }
            userErrors { field message }
          }
        }
        """
        result = self._gql(
            shop_domain, gql, {"input": {"id": gid, "price": price}},
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("productVariantUpdate", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {"variant": mutation_result.get("productVariant", {}), "user_errors": []}

    def _update_inventory_level(
        self,
        shop_domain: str,
        location_id: str,
        variant_id: str,
        available: int,
        reason: str,
        dry_run: bool,
    ) -> dict:
        """Set absolute available quantity for a variant at a location.

        Uses ``inventorySetQuantities`` mutation (2024-10+).
        """
        if not location_id:
            return {"error": "location_id is required for update_inventory_level."}
        if not variant_id:
            return {"error": "variant_id is required for update_inventory_level."}

        loc_gid = self._gid("Location", location_id)
        var_gid = self._gid("ProductVariant", variant_id)

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {
                    "inventorySetQuantities": {
                        "location_id": loc_gid,
                        "variant_id": var_gid,
                        "available": available,
                        "reason": reason or "correction",
                    }
                },
                "items_affected": 1,
            }

        # First resolve the inventory item ID from the variant
        resolve_gql = """
        query GetInventoryItem($variantId: ID!) {
          productVariant(id: $variantId) { inventoryItem { id } }
        }
        """
        resolve_result = self._gql(shop_domain, resolve_gql, {"variantId": var_gid})
        if "error" in resolve_result:
            return resolve_result

        item_id = (
            resolve_result.get("productVariant", {})
            .get("inventoryItem", {})
            .get("id", "")
        )
        if not item_id:
            return {"error": f"Could not resolve inventoryItem for variant {variant_id}"}

        set_gql = """
        mutation SetInventoryQuantity($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) {
            inventoryAdjustmentGroup {
              reason changes { name delta quantityAfterChange }
            }
            userErrors { field message }
          }
        }
        """
        variables = {
            "input": {
                "reason": reason or "correction",
                "quantities": [
                    {
                        "inventoryItemId": item_id,
                        "locationId": loc_gid,
                        "quantity": available,
                    }
                ],
                "ignoreCompareQuantity": True,
            }
        }
        result = self._gql(shop_domain, set_gql, variables, idempotency_key=self._idempotency_key())
        if "error" in result:
            return result

        mutation_result = result.get("inventorySetQuantities", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {
            "ok": True,
            "adjustment_group": mutation_result.get("inventoryAdjustmentGroup", {}),
        }

    def _tag_customer(
        self, shop_domain: str, customer_id: str, tags: list, dry_run: bool
    ) -> dict:
        """Append tags to a customer record (merges with existing tags)."""
        if not customer_id:
            return {"error": "customer_id is required for tag_customer."}
        if not tags:
            return {"error": "tags is required for tag_customer (list of strings)."}

        gid = self._gid("Customer", customer_id)

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {"customerUpdate": {"customer": {"id": gid, "tags": tags}}},
                "items_affected": 1,
            }

        # Fetch existing tags first so we can merge without overwriting
        fetch_gql = """
        query GetCustomerTags($id: ID!) { customer(id: $id) { tags } }
        """
        fetch_result = self._gql(shop_domain, fetch_gql, {"id": gid})
        if "error" in fetch_result:
            return fetch_result

        existing_tags: list = fetch_result.get("customer", {}).get("tags", [])
        merged_tags = list({*existing_tags, *tags})

        mutate_gql = """
        mutation TagCustomer($input: CustomerInput!) {
          customerUpdate(input: $input) {
            customer { id email tags }
            userErrors { field message }
          }
        }
        """
        result = self._gql(
            shop_domain, mutate_gql,
            {"input": {"id": gid, "tags": merged_tags}},
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("customerUpdate", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {
            "customer": mutation_result.get("customer", {}),
            "tags_added": tags,
            "user_errors": [],
        }

    def _create_draft_order(
        self, shop_domain: str, payload: dict, dry_run: bool
    ) -> dict:
        """Create a new draft order from a line-items payload.

        The ``payload`` dict is passed verbatim as ``DraftOrderInput``.
        Minimum required field: ``lineItems``.
        """
        if not payload:
            return {"error": "payload is required for create_draft_order (DraftOrderInput dict)."}
        if "lineItems" not in payload and "line_items" not in payload:
            return {"error": "payload must contain 'lineItems' for create_draft_order."}

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {"draftOrderCreate": {"draftOrder": payload}},
                "items_affected": len(payload.get("lineItems", payload.get("line_items", []))),
            }

        gql = """
        mutation CreateDraftOrder($input: DraftOrderInput!) {
          draftOrderCreate(input: $input) {
            draftOrder {
              id name status
              totalPriceSet { shopMoney { amount currencyCode } }
              invoiceUrl
            }
            userErrors { field message }
          }
        }
        """
        result = self._gql(
            shop_domain, gql, {"input": payload},
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("draftOrderCreate", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {
            "draft_order": mutation_result.get("draftOrder", {}),
            "user_errors": [],
        }

    def _create_discount_code(
        self, shop_domain: str, payload: dict, dry_run: bool
    ) -> dict:
        """Create a basic discount code (percentage or fixed-amount).

        The ``payload`` dict maps to ``DiscountCodeBasicInput``.  At minimum
        supply ``title``, ``code`` (in ``codes`` array), and ``customerGets``
        + ``value``.
        """
        if not payload:
            return {
                "error": (
                    "payload is required for create_discount_code. "
                    "Provide a DiscountCodeBasicInput dict with at least "
                    "'title', 'startsAt', 'customerGets', and 'codes'."
                )
            }

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {"discountCodeBasicCreate": {"codeDiscountNode": payload}},
                "items_affected": 1,
            }

        gql = """
        mutation CreateDiscountCode($basicCodeDiscount: DiscountCodeBasicInput!) {
          discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
            codeDiscountNode {
              id
              codeDiscount {
                ... on DiscountCodeBasic {
                  title status startsAt endsAt usageLimit
                  codes(first: 5) { edges { node { code } } }
                }
              }
            }
            userErrors { field message code }
          }
        }
        """
        result = self._gql(
            shop_domain, gql, {"basicCodeDiscount": payload},
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("discountCodeBasicCreate", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {
            "discount_node": mutation_result.get("codeDiscountNode", {}),
            "user_errors": [],
        }

    def _refund_order(
        self,
        shop_domain: str,
        order_id: str,
        payload: dict,
        amount: str,
        reason: str,
        approval_token: str,
        dry_run: bool,
    ) -> dict:
        """Issue a refund on an order.

        **Requires** a non-empty ``approval_token``.  The plugin validates
        presence only; token validity is enforced by guardrails.
        """
        if not approval_token.strip():
            return {
                "error": (
                    "approval_token required for refund_order. "
                    "This operation is destructive and must be approved "
                    "by the guardrails layer before execution."
                )
            }
        if not order_id:
            return {"error": "order_id is required for refund_order."}

        order_gid = self._gid("Order", order_id)

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {
                    "refundCreate": {
                        "order_id": order_gid,
                        "amount": amount,
                        "reason": reason,
                        "payload": payload,
                    }
                },
                "items_affected": 1,
            }

        # Build refund input from payload or amount
        refund_input: dict[str, Any] = {"orderId": order_gid}
        if reason:
            refund_input["note"] = reason
        if payload:
            refund_input.update(payload)
        elif amount:
            refund_input["transactions"] = [
                {"amount": amount, "kind": "REFUND", "gateway": "manual"}
            ]

        gql = """
        mutation RefundOrder($input: RefundInput!) {
          refundCreate(input: $input) {
            refund {
              id note
              totalRefundedSet { shopMoney { amount currencyCode } }
            }
            userErrors { field message }
          }
        }
        """
        result = self._gql(
            shop_domain, gql, {"input": refund_input},
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("refundCreate", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {"refund": mutation_result.get("refund", {}), "user_errors": []}

    def _fulfill_order(
        self, shop_domain: str, order_id: str, payload: dict, dry_run: bool
    ) -> dict:
        """Mark an order fulfillment as fulfilled via ``fulfillmentCreate``.

        The ``payload`` dict maps to ``FulfillmentInput``.  At minimum
        supply ``lineItemsByFulfillmentOrder`` listing the fulfillment order ID.
        """
        if not order_id:
            return {"error": "order_id is required for fulfill_order."}

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {"fulfillmentCreateV2": {"fulfillment": {"order_id": order_id, **( payload or {})}}},
                "items_affected": 1,
            }

        fulfillment_input = payload or {}
        if "orderId" not in fulfillment_input:
            fulfillment_input["orderId"] = self._gid("Order", order_id)

        gql = """
        mutation FulfillOrder($fulfillment: FulfillmentInput!) {
          fulfillmentCreateV2(fulfillment: $fulfillment) {
            fulfillment {
              id status
              trackingInfo { number url company }
            }
            userErrors { field message }
          }
        }
        """
        result = self._gql(
            shop_domain, gql, {"fulfillment": fulfillment_input},
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("fulfillmentCreateV2", {})
        if mutation_result.get("userErrors"):
            return {"error": mutation_result["userErrors"]}
        return {"fulfillment": mutation_result.get("fulfillment", {}), "user_errors": []}

    def _cancel_order(
        self,
        shop_domain: str,
        order_id: str,
        reason: str,
        amount: str,
        approval_token: str,
        dry_run: bool,
    ) -> dict:
        """Cancel an open order.

        **Requires** a non-empty ``approval_token``.
        """
        if not approval_token.strip():
            return {
                "error": (
                    "approval_token required for cancel_order. "
                    "This operation is destructive and must be approved "
                    "by the guardrails layer before execution."
                )
            }
        if not order_id:
            return {"error": "order_id is required for cancel_order."}

        order_gid = self._gid("Order", order_id)
        cancel_reason = reason.upper() if reason else "OTHER"

        if dry_run:
            return {
                "dry_run": True,
                "would_execute": {
                    "orderCancel": {
                        "orderId": order_gid,
                        "reason": cancel_reason,
                        "refund": bool(amount),
                    }
                },
                "items_affected": 1,
            }

        gql = """
        mutation CancelOrder(
          $orderId: ID!,
          $reason: OrderCancelReason!,
          $refund: Boolean!,
          $restock: Boolean!,
          $notifyCustomer: Boolean
        ) {
          orderCancel(
            orderId: $orderId,
            reason: $reason,
            refund: $refund,
            restock: $restock,
            notifyCustomer: $notifyCustomer
          ) {
            job { id done }
            orderCancelUserErrors { field message code }
          }
        }
        """
        variables = {
            "orderId": order_gid,
            "reason": cancel_reason,
            "refund": bool(amount),
            "restock": True,
            "notifyCustomer": True,
        }
        result = self._gql(
            shop_domain, gql, variables,
            idempotency_key=self._idempotency_key(),
        )
        if "error" in result:
            return result

        mutation_result = result.get("orderCancel", {})
        if mutation_result.get("orderCancelUserErrors"):
            return {"error": mutation_result["orderCancelUserErrors"]}
        return {"job": mutation_result.get("job", {}), "user_errors": []}

    # ------------------------------------------------------------------
    # execute  (main dispatcher)
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        # common
        shop_domain: str = "",
        # resource ids
        product_id: str = "",
        variant_id: str = "",
        order_id: str = "",
        customer_id: str = "",
        location_id: str = "",
        draft_order_id: str = "",
        discount_id: str = "",
        # filters / paging
        query: str = "",
        status: str = "",
        limit: int = 50,
        cursor: str = "",
        # write payloads
        payload: dict | None = None,
        tags: list | None = None,
        price: str = "",
        available: int = 0,
        reason: str = "",
        amount: str = "",
        # safety
        approval_token: str = "",
        dry_run: bool = True,
    ) -> dict:
        """Dispatch a Shopify Admin API operation.

        Args:
            operation: Operation name.  See class docstring for the full list.
            shop_domain: Shopify shop domain (``mystore.myshopify.com``).
                Falls back to ``SHOPIFY_SHOP_DOMAIN`` environment variable.
            product_id: Shopify product ID (numeric or GID).
            variant_id: Product variant ID (numeric or GID).
            order_id: Order ID (numeric or GID).
            customer_id: Customer ID (numeric or GID).
            location_id: Location ID (numeric or GID).
            draft_order_id: Draft order ID (numeric or GID).
            discount_id: Discount node ID (numeric or GID).
            query: Shopify search query string for list operations
                (e.g. ``"tag:sale"`` or ``"financial_status:paid"``).
            status: Status filter for ``list_orders``
                (``open`` / ``closed`` / ``any``) and ``list_draft_orders``
                (``open`` / ``completed``).
            limit: Page size, capped at 250. Defaults to ``50``.
            cursor: Pagination cursor from a previous response's
                ``end_cursor`` field.
            payload: Mutation input dict for write operations (e.g.
                ``ProductInput``, ``DraftOrderInput``,
                ``DiscountCodeBasicInput``, ``FulfillmentInput``).
            tags: List of tag strings for ``tag_customer``.
            price: New price string for ``update_variant_price``
                (e.g. ``"29.99"``).
            available: Absolute available quantity for
                ``update_inventory_level``.
            reason: Free-text reason for refunds/cancellations, or inventory
                adjustment reason (e.g. ``"correction"``).
            amount: Monetary amount string for ``refund_order`` and
                ``cancel_order`` (e.g. ``"15.00"``).
            approval_token: **Required** non-empty string for destructive
                operations (``refund_order``, ``cancel_order``).
            dry_run: When ``True`` (default), write operations return a
                preview dict without touching the API.  Set to ``False``
                to execute for real.

        Returns:
            A JSON-serialisable dict.  Error conditions return
            ``{"error": "<message>"}`` or ``{"error": [...]}``.

            Dry-run write operations return::

                {
                    "dry_run": true,
                    "would_execute": { ... },
                    "items_affected": N
                }
        """
        op = operation.strip().lower()

        # ---- Read operations ----------------------------------------
        if op == "list_products":
            return self._list_products(shop_domain, query, limit, cursor)

        if op == "get_product":
            return self._get_product(shop_domain, product_id)

        if op == "list_orders":
            return self._list_orders(shop_domain, status, query, limit, cursor)

        if op == "get_order":
            return self._get_order(shop_domain, order_id)

        if op == "list_customers":
            return self._list_customers(shop_domain, query, limit, cursor)

        if op == "get_customer":
            return self._get_customer(shop_domain, customer_id)

        if op == "list_inventory_levels":
            return self._list_inventory_levels(shop_domain, location_id, limit, cursor)

        if op == "list_locations":
            return self._list_locations(shop_domain, limit)

        if op == "list_draft_orders":
            return self._list_draft_orders(shop_domain, status, limit, cursor)

        if op == "list_discounts":
            return self._list_discounts(shop_domain, limit, cursor)

        # ---- Write operations ----------------------------------------
        if op == "update_product":
            return self._update_product(shop_domain, product_id, payload or {}, dry_run)

        if op == "update_variant_price":
            return self._update_variant_price(shop_domain, variant_id, price, dry_run)

        if op == "update_inventory_level":
            return self._update_inventory_level(
                shop_domain, location_id, variant_id, available, reason, dry_run
            )

        if op == "tag_customer":
            return self._tag_customer(shop_domain, customer_id, tags or [], dry_run)

        if op == "create_draft_order":
            return self._create_draft_order(shop_domain, payload or {}, dry_run)

        if op == "create_discount_code":
            return self._create_discount_code(shop_domain, payload or {}, dry_run)

        if op == "refund_order":
            return self._refund_order(
                shop_domain, order_id, payload or {}, amount, reason, approval_token, dry_run
            )

        if op == "fulfill_order":
            return self._fulfill_order(shop_domain, order_id, payload or {}, dry_run)

        if op == "cancel_order":
            return self._cancel_order(
                shop_domain, order_id, reason, amount, approval_token, dry_run
            )

        # ---- Unknown operation ----------------------------------------
        all_ops = sorted(_READ_OPS | _WRITE_OPS)
        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                f"Valid operations: {', '.join(all_ops)}."
            )
        }
