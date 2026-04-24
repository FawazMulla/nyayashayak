from django import template

register = template.Library()

@register.filter
def split_csv(value):
    """Split a comma-separated string into a list. Usage: {{ value|split_csv }}"""
    if not value:
        return []
    return [s.strip() for s in str(value).split(",") if s.strip()]
