import io, os

def test_prompt_contiene_campos_clave():
    # Cargar el archivo de texto del prompt sin importar el módulo (para no requerir openai instalado).
    here = os.path.dirname(os.path.abspath(__file__))
    llm_path = os.path.abspath(os.path.join(here, "..", "app", "llm.py"))
    with open(llm_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert '"q"' in src
    assert '"must"' in src
    assert '"not"' in src
    assert '"units"' in src
    assert '"decision"' in src
    assert '"questions"' in src
