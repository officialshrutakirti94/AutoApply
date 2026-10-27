"""LangGraph agent: decisions only.

The extension owns the page and performs the actions; nothing in this package
reads a DOM node, holds a selector or opens a URL. Keep it that way: this is the
trust boundary described in section 6 of the plan.
"""
