
app_name = "bom"
app_title = "BOM"
app_publisher = "ummu"
app_description = "Custom BOM and Order-Based Manufacturing"
app_email = "umer@aitsind.com"
app_license = "mit"

# Custom BOM JavaScript
doctype_js = {
    "BOM": "public/js/bom.js"
}

# Override BOM Controller
override_doctype_class = {
    "BOM": "bom.overrides.bom.CustomBOM"
}

# Fixtures
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ["BOM", "Work Order"]]
        ]
    },
    {
        "dt": "Property Setter",
        "filters": [
            ["doc_type", "=", "BOM"],
            ["field_name", "=", "item"],
            ["property", "=", "reqd"]
        ]
    }
]