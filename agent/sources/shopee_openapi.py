"""Shopee Affiliate Open API (GraphQL) — authorized discovery with real commission/sales data.

STATUS: written against the publicly described request format (SHA256 signature of
appId + timestamp + payload + secret); NOT yet executed against the live API because the operator's
account does not have Open API access yet. Verify field names against the official docs when access
is granted. Credentials come only from env: SHOPEE_AFF_APP_ID, SHOPEE_AFF_SECRET.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request

from ..config import Config, secret
from ..schemas import Candidate

QUERY = """query($keyword:String,$limit:Int,$page:Int,$sortType:Int){
  productOfferV2(keyword:$keyword,limit:$limit,page:$page,sortType:$sortType){
    nodes{ itemId productName productLink offerLink imageUrl price commissionRate sales ratingStar shopName }
    pageInfo{ page limit hasNextPage }
  }
}"""


def sign(app_id: str, secret_key: str, payload: str, ts: int) -> str:
    return hashlib.sha256(f"{app_id}{ts}{payload}{secret_key}".encode()).hexdigest()


class ShopeeOpenAPISource:
    name = "shopee_openapi"

    def __init__(self, keyword: str | None = None, sort_type: int = 2):
        self.keyword = keyword
        self.sort_type = sort_type  # verify meaning of sortType values in official docs

    def search(self, cfg: Config) -> list[Candidate]:
        app_id, key = secret("SHOPEE_AFF_APP_ID"), secret("SHOPEE_AFF_SECRET")
        if not app_id or not key:
            raise RuntimeError("Shopee Affiliate Open API credentials missing (SHOPEE_AFF_APP_ID / "
                               "SHOPEE_AFF_SECRET). Account access not granted yet → use csv/manual source.")
        body = json.dumps({"query": QUERY, "variables": {
            "keyword": self.keyword or cfg.source.keyword, "limit": cfg.source.limit, "page": 1,
            "sortType": self.sort_type}}, separators=(",", ":"))
        ts = int(time.time())
        req = urllib.request.Request(cfg.source.openapi_url, data=body.encode(), method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={sign(app_id, key, body, ts)}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        if data.get("errors"):
            raise RuntimeError(f"Open API error: {data['errors']}")
        out = []
        for n in data["data"]["productOfferV2"]["nodes"]:
            out.append(Candidate(
                source="shopee_openapi", source_ref=str(n.get("itemId")), name=n["productName"],
                listing_url=n.get("productLink", ""), affiliate_link=n.get("offerLink"),
                shop_name=n.get("shopName"), price=float(n["price"]) if n.get("price") else None,
                commission_rate=float(n["commissionRate"]) if n.get("commissionRate") else None,
                commission_verified=n.get("commissionRate") is not None,
                sales_count=int(n["sales"]) if n.get("sales") is not None else None,
                rating=float(n["ratingStar"]) if n.get("ratingStar") else None,
                image_urls=[n["imageUrl"]] if n.get("imageUrl") else [],
                limitations=["Open API returns one cover image; more images need operator/licensed sources"]))
        return out
