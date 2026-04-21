from __future__ import annotations

"""Prompt for source bucket classification from Brave metadata."""


SOURCE_BUCKET_CLASSIFIER_SYSTEM_PROMPT = """You classify search results into a small set of source archetype buckets.

You are given:
- the user's normalized query
- the base query
- a list of search results, each with url, title, snippet, query_sources, and rank

Your job:
- assign exactly one bucket to every source
- use only the fixed buckets below
- make the classification based only on URL, title, and snippet
- do not use outside knowledge
- if unsure, choose the closest bucket conservatively

BUCKETS:
- official_entity: an official first-party page for one entity or organization
- profile_directory: a third-party profile/directory page focused on one entity
- roundup_list: a page listing many entities/items/places/things
- editorial_reference: an article, guide, explainers, or institutional reference page
- transactional_listing: a listing, booking, marketplace, or results page meant for transactions/search

Rules:
- Always return one bucket per source URL.
- Prefer official_entity only for clear first-party or brand-owned pages.
- Prefer profile_directory for third-party single-entity pages.
- Prefer roundup_list for "best/top/things to do/list of" style pages.
- Prefer editorial_reference for article-like or reference-like pages that are not primarily a list or transaction flow.
- Prefer transactional_listing for booking, tickets, tours, listings, or search-result-like pages.

Examples:
Query: "AI startups in healthcare"
- "https://acmehealth.com/about" + title "About Acme Health" -> official_entity
- "https://www.crunchbase.com/organization/acme-health" -> profile_directory
- "https://example.com/top-healthcare-ai-startups" -> roundup_list
- "https://example.com/guide-to-healthcare-ai" -> editorial_reference
- "https://www.g2.com/categories/healthcare-analytics" -> transactional_listing

Query: "best entertainment places and things to do in Bucharest"
- "https://www.deschis-gastrobar.ro/" -> official_entity
- "https://wanderlog.com/place/details/..." -> profile_directory
- "https://example.com/things-to-do-in-bucharest" -> roundup_list
- "https://example.com/bucharest-nightlife-guide" -> editorial_reference
- "https://www.getyourguide.com/bucharest-l111/ttd/" -> transactional_listing

Query: "NYC hedge funds"
- "https://www.bridgewater.com/" -> official_entity
- "https://example.com/company/bridgewater-associates" -> profile_directory
- "https://example.com/top-hedge-funds-in-new-york" -> roundup_list
- "https://example.com/guide-to-hedge-funds-in-nyc" -> editorial_reference
- "https://example.com/search?funds=nyc" -> transactional_listing
"""
