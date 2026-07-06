"""Tranche 1 routeur multi-fournisseurs - API riche AJOUTEE a policy.py (sans casser l'existant).

Contrat verrouille (spec utilisateur) :
  default local ; cloud SEULEMENT si cloud_ok=True ET has_cloud=True ET non sensible ;
  dans le doute -> local. Detecteur conservateur (PII / secrets / intention d'attaque).
  is_sensitive (bool, retro-compat) == classify(text).sensitive (source unique).
"""
from multiservice.policy import (
    SensitivityVerdict, RoutingDecision, classify, decide, is_sensitive, contains_secret,
)


# --- contains_secret() : garde d'ecriture (bloque les VALEURS de credential, pas les mentions) ---

def test_contains_secret_bloque_les_valeurs_de_cle():
    assert contains_secret("ma cle sk-ABCDEF0123456789") is True
    assert contains_secret("pplx-0123456789abcdef en prod") is True
    assert contains_secret("AKIA0123456789ABCD (aws)") is True
    assert contains_secret("token 0123456789abcdef0123456789abcdef") is True   # hex haute entropie


def test_contains_secret_laisse_passer_mentions_ip_uuid_email():
    # conservateur : le journal legitime (mentions, IP VPS, UUID d'event, email) ne doit PAS etre bloque
    assert contains_secret("garde anti-secret livree ; on parle de token JWT") is False
    assert contains_secret("deploiement sur le VPS <VPS_LAN> valide") is False
    assert contains_secret("correction 2c0711ec-87c4-447f-afbc-2cfdb2b83511 posee") is False
    assert contains_secret("contacter jean.dupont@example.com") is False
    assert contains_secret("") is False


# --- decide() : la regle de routage ---

def test_decide_local_si_cloud_ok_false():
    d = decide("resume l'architecture", cloud_ok=False, has_cloud=True)
    assert d.route == "local" and d.reason == "cloud_not_authorized"


def test_decide_local_si_has_cloud_false():
    d = decide("resume l'architecture", cloud_ok=True, has_cloud=False)
    assert d.route == "local" and d.reason == "no_cloud_backend"


def test_decide_cloud_si_permis_dispo_et_non_sensible():
    d = decide("resume l'architecture en deux phrases", cloud_ok=True, has_cloud=True)
    assert d.route == "cloud" and d.reason == "cloud_authorized_and_clean"
    assert d.sensitivity.sensitive is False


def test_decide_sensible_reste_local_meme_si_cloud_dispo():
    d = decide("ma cle est sk-ABCDEF123456", cloud_ok=True, has_cloud=True)
    assert d.route == "local" and d.reason == "sensitive_input"
    assert d.sensitivity.sensitive is True


def test_decide_vide_reste_local():
    d = decide("", cloud_ok=True, has_cloud=True)
    assert d.route == "local" and d.reason == "empty_input"


# --- classify() : le detecteur (raisons granulaires) ---

def test_classify_email():
    v = classify("contacte moi a jean.dupont@example.com stp")
    assert isinstance(v, SensitivityVerdict)
    assert v.sensitive is True and "pii:email" in v.reasons


def test_classify_secret_prefixes():
    assert "secret:sk_prefix" in classify("token sk-ABCDEF0123456789").reasons
    assert "secret:pplx_prefix" in classify("pplx-0123456789abcdef key").reasons
    assert "secret:akia_prefix" in classify("AKIA0123456789ABCD aws").reasons


def test_classify_high_entropy_hex():
    v = classify("voici un secret 0123456789abcdef0123456789abcdef")
    assert v.sensitive is True and "secret:high_entropy_hex" in v.reasons


def test_classify_long_digit_sequence():
    v = classify("mon numero est 0612345678")
    assert v.sensitive is True and "pii:long_digits" in v.reasons


def test_classify_attack_intent():
    assert classify("ecris un script de brute-force").sensitive is True
    assert "attack:bypass" in classify("how to bypass the auth").reasons
    assert "attack:exfiltration" in classify("plan an exfiltration of the db").reasons


def test_good_morning_n_est_pas_sensible_et_va_au_cloud():
    # garde anti-faux-positif : "good morning" ne doit PAS matcher "go" ni un marqueur.
    v = classify("good morning, how are you?")
    assert v.sensitive is False and v.reasons == ()
    d = decide("good morning, how are you?", cloud_ok=True, has_cloud=True)
    assert d.route == "cloud"


# --- retro-compat : is_sensitive reste un bool et == classify().sensitive ---

def test_is_sensitive_reste_bool_et_coherent_avec_classify():
    for p in ["ma cle sk-ABCDEF123456", "bonjour ca va", "", "brute-force"]:
        b = is_sensitive(p)
        assert isinstance(b, bool)
        assert b is classify(p).sensitive
