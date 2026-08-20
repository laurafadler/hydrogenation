import json
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

INPUT_FILE = Path("ro-crate-metadata.json")
OUTPUT_FILE = Path("hydrogenation_types_and_properties.txt")


# JSON-LD keywords that are not considered properties
JSONLD_KEYWORDS = {
    "@context",
    "@id",
    "@type",
    "@value",
    "@language",
    "@list",
    "@set",
    "@graph",
    "@reverse",
    "@index",
    "@base",
    "@vocab",
    "@container",
    "@nest",
}


# ============================================================
# Helper functions
# ============================================================

def is_entity(value):
    """
    Returns True if value represents an entity reference.

    Example:
        {"@id": "#Vessel"}

    Also accepts objects that contain additional information,
    as long as they have an @id.
    """
    return isinstance(value, dict) and "@id" in value


def is_inline_value(value):
    """
    Returns True if value is an inline value.

    Examples:
        {"@value": 300}
        {"@type": "xsd:double", "@value": 300}
    """
    return isinstance(value, dict) and "@value" in value


def classify_single_value(value):
    """
    Classifies a single property value.

    Possible return values:
        ENTITY
        INLINE VALUE
        VALUE
    """

    if is_entity(value):
        return "ENTITY"

    if is_inline_value(value):
        return "INLINE VALUE"

    return "VALUE"


def classify_value(value):
    """
    Classifies the value of a property.

    Lists are checked element by element.

    A homogeneous list gets the corresponding list category.
    A heterogeneous list is classified as MIXED.

    Examples:
        [{"@id": "#A"}, {"@id": "#B"}]
            -> ENTITY LIST

        [{"@value": 1}, {"@value": 2}]
            -> INLINE VALUE

        ["A", "B"]
            -> VALUE

        [{"@id": "#A"}, "B"]
            -> MIXED
    """

    if not isinstance(value, list):
        return classify_single_value(value)

    # Empty lists
    if len(value) == 0:
        return "VALUE"

    categories = set()

    for item in value:
        categories.add(classify_single_value(item))

    # Exactly one category throughout the list
    if len(categories) == 1:
        category = next(iter(categories))

        if category == "ENTITY":
            return "ENTITY LIST"

        if category == "INLINE VALUE":
            return "INLINE VALUE"

        if category == "VALUE":
            return "VALUE"

    # Different structures inside the list
    return "MIXED"


# ============================================================
# Recursive extraction
# ============================================================

def collect_information(obj, types, properties):
    """
    Recursively walks through the complete JSON structure.

    types:
        Set containing all encountered @type values.

    properties:
        Dictionary:
            property_name -> set of observed categories
    """

    if isinstance(obj, dict):

        # ----------------------------------------------------
        # Collect @type
        # ----------------------------------------------------

        if "@type" in obj:
            type_value = obj["@type"]

            if isinstance(type_value, list):
                for type_item in type_value:
                    if isinstance(type_item, str):
                        types.add(type_item)

            elif isinstance(type_value, str):
                types.add(type_value)

        # ----------------------------------------------------
        # Collect properties
        # ----------------------------------------------------

        for key, value in obj.items():

            # Ignore JSON-LD keywords
            if key in JSONLD_KEYWORDS:
                continue

            # This is a property
            category = classify_value(value)

            if key not in properties:
                properties[key] = set()

            properties[key].add(category)

            # Continue recursively
            collect_information(value, types, properties)

    elif isinstance(obj, list):

        for item in obj:
            collect_information(item, types, properties)


# ============================================================
# Resolve final property categories
# ============================================================

def resolve_property_categories(properties):
    """
    Converts all observed categories into one final category.

    If a property occurs with more than one structure,
    it is classified exclusively as MIXED.

    Example:

        {
            "ex:foo": {"ENTITY", "ENTITY LIST"}
        }

    becomes:

        {
            "ENTITY": [],
            "ENTITY LIST": [],
            "MIXED": ["ex:foo"]
        }
    """

    result = {
        "ENTITY": [],
        "ENTITY LIST": [],
        "INLINE VALUE": [],
        "VALUE": [],
        "MIXED": [],
    }

    for property_name, categories in properties.items():

        if len(categories) == 1:
            category = next(iter(categories))
            result[category].append(property_name)

        else:
            result["MIXED"].append(property_name)

    # Sort everything alphabetically
    for category in result:
        result[category].sort(key=str.lower)

    return result


# ============================================================
# Write output
# ============================================================

def write_output(types, property_categories, output_file):

    with output_file.open("w", encoding="utf-8") as file:

        # ----------------------------------------------------
        # Types
        # ----------------------------------------------------

        file.write("=" * 70 + "\n")
        file.write("TYPES\n")
        file.write("=" * 70 + "\n\n")

        for type_name in sorted(types, key=str.lower):
            file.write(f"{type_name}\n")

        file.write("\n")

        # ----------------------------------------------------
        # Properties
        # ----------------------------------------------------

        file.write("=" * 70 + "\n")
        file.write("PROPERTIES\n")
        file.write("=" * 70 + "\n\n")

        for category in [
            "ENTITY",
            "ENTITY LIST",
            "INLINE VALUE",
            "VALUE",
            "MIXED",
        ]:

            file.write(f"--- {category} ---\n\n")

            for property_name in property_categories[category]:
                file.write(f"{property_name}\n")

            file.write("\n")


# ============================================================
# Main
# ============================================================

def main():

    # --------------------------------------------------------
    # Check input file
    # --------------------------------------------------------

    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found:")
        print(f"       {INPUT_FILE}")
        return

    print(f"Reading: {INPUT_FILE}")

    # --------------------------------------------------------
    # Load JSON-LD
    # --------------------------------------------------------

    try:
        with INPUT_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError as error:
        print("\nERROR: The file could not be parsed as JSON.")
        print(f"Line:   {error.lineno}")
        print(f"Column: {error.colno}")
        print(f"Message: {error.msg}")
        return

    # --------------------------------------------------------
    # Collect information
    # --------------------------------------------------------

    types = set()
    properties = {}

    collect_information(
        data,
        types,
        properties
    )

    # --------------------------------------------------------
    # Resolve property categories
    # --------------------------------------------------------

    property_categories = resolve_property_categories(properties)

    # --------------------------------------------------------
    # Write output
    # --------------------------------------------------------

    write_output(
        types,
        property_categories,
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print("\nDone!")
    print("-" * 50)

    print(f"Types found:       {len(types)}")
    print(f"Properties found:  {len(properties)}")
    print()

    for category in [
        "ENTITY",
        "ENTITY LIST",
        "INLINE VALUE",
        "VALUE",
        "MIXED",
    ]:
        print(
            f"{category:<15}: "
            f"{len(property_categories[category])}"
        )

    print()
    print(f"Output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()