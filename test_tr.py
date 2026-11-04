import sys
sys.path.insert(0, "tools")
import convert_templates as c

t = "${product} ? @{/inventory/{id}/movimientos(id=${product.id})} : @{/inventory/movimientos}"
print("convert_at:", c.convert_at("/inventory/{id}/movimientos(id=${product.id})"))
print("_link_expr:", c._link_expr("@{/inventory/{id}/movimientos(id=${product.id})}"))
print("link_attr :", c.link_attr(t))
print("tab:", c.translate(t))
