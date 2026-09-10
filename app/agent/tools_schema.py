# app/agent/tools_schema.py

"""
مخطط الأدوات — Tools Schema

يُرسَل إلى Gemini مع كل طلب.
"""

from typing import Any, Dict, List


TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": "save_lead_info",
        "description": (
            "احفظ معلومة جديدة عن العميل المحتمل. "
            "استدعِ هذه الأداة فقط عندما يذكر العميل المعلومة صراحةً. "
            "لا تستنتج معلومات لم يقلها."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": [
                        "name",
                        "company",
                        "contact",
                        "project_type",
                        "problem",
                        "desired_solution",
                        "budget",
                        "timeline",
                    ],
                    "description": "اسم الحقل المراد حفظه",
                },
                "value": {
                    "type": "string",
                    "description": "القيمة كما ذكرها العميل",
                },
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "update_lead_stage",
        "description": (
            "حدّث مرحلة العميل في الـ funnel عندما يظهر "
            "تقدم واضح في المحادثة."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stage": {
                    "type": "string",
                    "enum": [
                        "qualifying",
                        "qualified",
                        "contact_requested",
                        "ready_to_buy",
                        "lost",
                    ],
                },
                "reason": {
                    "type": "string",
                    "description": "سبب التحديث",
                },
            },
            "required": ["stage"],
        },
    },
    {
        "name": "search_knowledge",
        "description": (
            "ابحث في قاعدة معرفة جمال للحصول على معلومات دقيقة "
            "عن خدمة أو تقنية أو سعر. استخدمها عندما لا تكون "
            "المعلومة واضحة في السياق."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "نص البحث",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "request_human_handoff",
        "description": (
            "اطلب تحويل المحادثة لبشري (جمال). "
            "استخدمها فقط عند: "
            "طلب العميل التحدث مع شخص، "
            "أو سؤال خارج نطاق معرفتك، "
            "أو عميل ساخن يطلب عرضاً رسمياً، "
            "أو عميل محبط."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "سبب التصعيد",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "notify_owner",
        "description": (
            "أرسل إشعاراً لجمال. لا تستخدمها إلا عند lead ساخن "
            "أو طلب صريح من العميل."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "نص الإشعار",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
            },
            "required": ["message"],
        },
    },
]
