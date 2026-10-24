"""The two letters that used to be written to a path named after the tenant.

`pdf/Mahnung_<tenant>.pdf` was one path for every landlord on a deployment.
Two landlords with a tenant of the same name wrote to the same file, and since
the endpoint builds the document and then reads that path back, one could be
handed the other's letter — the other tenancy's address and arrears inside it.
A name long enough also failed outright (OSError: File name too long).

Both now build into a buffer, so there is no name to collide and nothing on
disk to read back.
"""
import os

import pytest

pytest.importorskip("reportlab")

from pdfgen import generate_mahnung, invoice_pdf


def _files_in(path="pdf"):
    return set(os.listdir(path)) if os.path.isdir(path) else set()


def test_a_mahnung_comes_back_as_a_document_not_a_path():
    before = _files_in()
    out = generate_mahnung("Max Müller", 1250.00, "Musterstr. 1, 10115 Berlin")
    assert isinstance(out, bytes)
    assert out.startswith(b"%PDF")
    assert _files_in() == before, "a letter was left on disk"


def test_two_landlords_with_the_same_tenant_name_get_their_own_letter():
    a = generate_mahnung("Max Müller", 100.00, "Aweg 1, 10115 Berlin")
    b = generate_mahnung("Max Müller", 999.00, "Bweg 2, 12043 Berlin")
    assert a.startswith(b"%PDF") and b.startswith(b"%PDF")
    # Same name, different letters: nothing is shared between the two calls.
    assert a != b


@pytest.mark.parametrize("name", [
    "A" * 400,                       # OSError: File name too long
    "../../etc/passwd",              # never a path, but it was interpolated into one
    "Max/Müller",
    "Max\\Müller",
    "Max\tMüller",
])
def test_an_awkward_tenant_name_is_just_a_name(name):
    before = _files_in()
    out = generate_mahnung(name, 50.0, "Musterstr. 1, 10115 Berlin")
    assert out.startswith(b"%PDF")
    assert _files_in() == before


def test_an_abrechnung_comes_back_with_its_result():
    # No utility sections: every one of them is optional, and what is being
    # pinned here is the return shape, not the arithmetic (which has its own
    # tests in test_logic.py).
    before = _files_in()
    pdf, total = invoice_pdf(tenant="Max Müller",
                             address="Musterstr. 1, 10115 Berlin")
    assert isinstance(pdf, bytes) and pdf.startswith(b"%PDF")
    assert total == 0.0
    assert _files_in() == before
