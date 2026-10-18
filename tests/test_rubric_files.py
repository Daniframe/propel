"""The rubrics that ship with the package, and their catalogue.

A rubric is prompt text: the annotator reads it verbatim, so any change to it changes every
prompt built from it. These tests make every change deliberate, keep the catalogue and the
files in step, and run the recommended structure checks on every rubric.
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest

from propensity.annotation.rubrics import (
    RUBRICS_DIR,
    available_dimensions,
    available_versions,
    check_rubric,
    load_dimensions,
    rubric_path_for,
)

ROOT = Path(__file__).resolve().parents[1]

# Update a hash only when you mean to change what annotators read, and remember that annotations
# made before and after the change are not comparable. A new version is a new file and a new pin.
PINNED_SHA256 = {
    "RA/RA_v1.md": "eaf6978d3d2228b914ef69333308ec4330bacd6ca3b992ae2e031ba0408cd540",
    "RA/RA_v2.md": "166969c2ae87ce43834d428d0d805981d1f1fe6d262709283bbb75b52f46fae3",
    "Ex/Ex_v1.md": "dc446ddc4a78c7246f35065dc5873656c4e4028d1a34b05b2a46a30a64635b03",
    "Ul/Ul_v1.md": "0e31ec68be25ae8812d41b2a89f1199f99a229683fdd8d6a3360bdc7b1fa6b7a",
    "BR/BR_v1.md": "98c3fbd56d568fb0ad5b3a4c4a81b9e93a3fe6f8d9070e49285365c48a6fa9c2",
    "Af/Af_v1.md": "54d816c379b9234571826ebf6b53a9b9db3260833d61b6f940c085dff35a6b26",
    "Ag/Ag_v1.md": "a9aeb2c91560c25c241ee290fcb42d43246845b3d94a4df0c7c5f4c744949487",
    "Al/Al_v1.md": "8e221ebde56a7fce560afe5569ba6b75fa1b1aa6bea9c2b7719b6b3adc5381ca",
    "Cm/Cm_v1.md": "2cc28a7038a7b8e84daf5e681ac3fb9247d3704eb51ce9445c80419f243b0097",
    "Co/Co_v1.md": "da91de32bcf855fc82b92f921d11e3033089942431aed284f1dae0179d3f4609",
    "IM/IM_v1.md": "89ab9919a408ef1c1d19ef3f15fa3cd20bb099bef9727f964702a22444017971",
    "Mc/Mc_v1.md": "a024b04ba7e268086584140fc5241d4ea94c737df2ba70a45c57f5789f9bef5c",
    "Ne/Ne_v1.md": "7d0d974672305a0badf52bf3434095161390ad716d35193c5256cb83158cd28a",
    "Nr/Nr_v1.md": "a0b1274cc805f9bdab2589e63fe24ab79e023738768b4a968ccc444f8602d88c",
    "Op/Op_v1.md": "3d54259ca2c401aba195c27a2a709d3db9afe3bf6f8c2a792139c908a266c4a4",
    "Ps/Ps_v1.md": "87b9ee2c9b78b43bac0886c9bd4cceb22548c325a58612c45a2a863b4d9cc0e2",
    # Added in 0.4.0, from the propensity hierarchy.
    "Ac/Ac_v1.md": "00e157fee509500b3fda2a4b55c9b111ee46d9eb970b1d43f0e33f81513a4e48",
    "Bn/Bn_v1.md": "ddbc231fc0ea9929a2a6e9c028aeb483527055a61a9632f54eeaecbb0c6cab78",
    "Cf/Cf_v1.md": "ce40bc886ffac53c429c1ee44199e3b8de63d145b471afc4021a96faddbe8ac7",
    "Cs/Cs_v1.md": "a2f0f2812ce8432a05262cafde77328438273421e94d967d09c65e0e97558510",
    "Ex/Ex_v2.md": "c61183a0dc9a88176a067749203b60b0493891a82ee24196eec99b08072c72be",
    "He/He_v1.md": "f704b5cd3087a9a08c6655a064549a2bc13ce91269dec207ac852388eaca1b74",
    "Np/Np_v1.md": "c71ae323da42a79d3a36d968b4b65992b1ee21335ce9ad5c528808cdc53d7386",
    "Pw/Pw_v1.md": "0aa7d7b26ec73132f894ceaab0f0868bec9121845eb4ef133c15950255751ccc",
    "SD/SD_v1.md": "0a92f8b60220f1a72ab21523138e3ff55cd3d93574d8497c25e43e2dc209ce09",
    "Sc/Sc_v1.md": "84d648822b195b4a645028b3c7d7f9ef034e2fc14e72185c8d3fb04ca1fb821a",
    "St/St_v1.md": "dc619e364e081a26ee29cdd109c33fd2193fd27097e659ee34b8900221a81604",
    "TD/TD_v1.md": "2eeac288b848e97fc42a21469e7bcc9f1dff05066064e4e4b22a3154a4073e2a",
    "Tr/Tr_v1.md": "ff2164dff734352525605c6329b92c3967d911ffc81a69f7754ca640367bcfbd",
    "Ul/Ul_v2.md": "9c89776a815c702d897ac3a8182d6bf4ddf6c53c5686f831c25ff19cf3df57ec",
    "Un/Un_v1.md": "e71594876713b60f78a839cd167b0644ece5d8f8fcfb0a76f879700de78dc532",
    "presentation.md": "ac528f3004e2501bbc0335d8931f237dd006ffdee8a21744816c73398d6f46a1",  # sans final newlines
}


def rubric_files():
    return sorted(path.relative_to(RUBRICS_DIR).as_posix() for path in RUBRICS_DIR.glob("*/*.md"))


def pinned_bytes(relpath):
    """The bytes a pin covers. presentation.md's final newlines are left out: the prompt builder
    ignores them, so an editor that adds or strips one changes no prompt. A rubric file's final
    newline is part of every prompt, so it is pinned with the rest."""
    data = (RUBRICS_DIR / relpath).read_bytes()
    return data.rstrip(b"\n") if relpath == "presentation.md" else data


# --- bytes ---------------------------------------------------------------------------------

@pytest.mark.parametrize("relpath", sorted(PINNED_SHA256))
def test_rubric_bytes_are_pinned(relpath):
    digest = hashlib.sha256(pinned_bytes(relpath)).hexdigest()
    assert digest == PINNED_SHA256[relpath], (
        f"{relpath} changed. If that was deliberate, update PINNED_SHA256; "
        "check first that no editor added or removed a final newline.")


def test_every_rubric_file_is_pinned():
    assert {*rubric_files(), "presentation.md"} == set(PINNED_SHA256)


@pytest.mark.parametrize("relpath", sorted(PINNED_SHA256))
def test_rubric_is_utf8_with_unix_line_endings(relpath):
    data = (RUBRICS_DIR / relpath).read_bytes()
    data.decode("utf-8")
    assert b"\r" not in data


def test_the_presentation_block_opens_and_closes_as_the_prompt_expects():
    # It closes the <rubric> tag the prompt opens; the question follows on the next line (the
    # prompt supplies that line break, so the file's own final newline does not matter).
    text = (RUBRICS_DIR / "presentation.md").read_text(encoding="utf-8")
    assert text.startswith("</rubric>")
    assert text.rstrip("\n").endswith("Annotate the following task:")
    assert "<FINAL_RANGE>[LB, UB]</FINAL_RANGE>" in text


# --- recommended checks -------------------------------------------------------------------
# Recommendations, not requirements: a rubric that misses some still ships and is used, with a
# warning when it annotates. docs/dimensions.md lists each current rubric's result, and the
# test below keeps that page up to date, so a gap is always visible.

@pytest.mark.parametrize("relpath", rubric_files())
def test_the_recommended_checks_run_on_every_rubric(relpath):
    misses = check_rubric((RUBRICS_DIR / relpath).read_text(encoding="utf-8"))
    assert isinstance(misses, list) and all(isinstance(miss, str) for miss in misses)


# --- the catalogue -------------------------------------------------------------------------

def test_every_rubric_folder_is_catalogued_and_every_entry_has_its_rubric():
    catalogue = load_dimensions()
    assert sorted(catalogue) == available_dimensions()
    for code, dimension in catalogue.items():
        assert dimension.code == code
        assert rubric_path_for(code).exists(), f"{code}: no rubric for its version {dimension.version}"
        assert dimension.version in available_versions(code)


def test_trait_names_are_unique_and_poles_are_given():
    catalogue = load_dimensions()
    names = [dimension.name for dimension in catalogue.values()]
    assert len(names) == len(set(names))
    for dimension in catalogue.values():
        assert dimension.negative and dimension.positive and dimension.summary, dimension.code


def test_the_catalogue_page_in_the_docs_is_up_to_date():
    spec = importlib.util.spec_from_file_location("make_dimensions", ROOT / "docs" / "make_dimensions.py")
    make_dimensions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_dimensions)
    page = (ROOT / "docs" / "dimensions.md").read_text(encoding="utf-8")
    assert page == make_dimensions.render(), "run: python docs/make_dimensions.py"
