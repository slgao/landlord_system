"""Which meters a WG room should be read for.

A WG is one `apartments` row per room, all sharing a property_id + `flat`. The
flat's Strom/Gas/Wasser meters sit on whichever room was entered first, so a
room asked for "its" meters by apartment_id alone finds none — which is how a WG
Übergabeprotokoll ended up with no Zählerstände. The `scope` column carries the
distinction that fixes it.
"""
from api.routers.meters import meter_belongs_to_room

GROSS, MITTEL, KLEIN = 3, 2, 1      # the three rooms of one flat


def test_your_own_shared_meter_counts():
    assert meter_belongs_to_room(KLEIN, "shared", KLEIN) is True


def test_a_flatmates_shared_meter_counts_too():
    # The whole point: the flat's Stromzähler is registered on one room but read
    # for all of them.
    assert meter_belongs_to_room(GROSS, "shared", KLEIN) is True


def test_your_own_room_scoped_meter_counts():
    # A Heizkostenverteiler is yours precisely because it is registered on you,
    # so its 'room' scope must not exclude it from your own protocol.
    assert meter_belongs_to_room(KLEIN, "room", KLEIN) is True


def test_a_flatmates_room_scoped_meter_does_not():
    # The exception the landlord asked for: per-room Heizkostenverteiler must
    # not leak onto a flatmate's sheet.
    assert meter_belongs_to_room(GROSS, "room", KLEIN) is False
    assert meter_belongs_to_room(MITTEL, "room", KLEIN) is False


def test_a_missing_scope_is_treated_as_shared():
    # Rows predating the scope column carry NULL; the historical behaviour for
    # Strom/Gas/Wasser was shared, and defaulting to 'room' would instead hide
    # the flat's main meter from every room but one.
    assert meter_belongs_to_room(GROSS, None, KLEIN) is True
    assert meter_belongs_to_room(GROSS, "", KLEIN) is True


def test_a_standalone_apartment_sees_only_itself():
    # Not a WG: the room id is the apartment id, so both scopes resolve to True
    # for its own meters and nothing else can reach it (the query only ever
    # offers meters from the same flat).
    solo = 42
    assert meter_belongs_to_room(solo, "shared", solo) is True
    assert meter_belongs_to_room(solo, "room", solo) is True


def test_the_wintersteinstr_shape():
    # The real case: one shared Strom meter on the big room, and (once entered)
    # a Heizkostenverteiler per room. The small room must get the shared Strom
    # and only its own Verteiler.
    meters = [
        ("strom", GROSS, "shared"),
        ("heizung", GROSS, "room"),
        ("heizung", MITTEL, "room"),
        ("heizung", KLEIN, "room"),
    ]
    got = [(t, a) for (t, a, s) in meters if meter_belongs_to_room(a, s, KLEIN)]
    assert got == [("strom", GROSS), ("heizung", KLEIN)]
