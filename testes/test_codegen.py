import json

from nucleo import codegen, projeto


CFG = {
    "timeout_imagem": 5,
    "confianca_imagem": 0.85,
    "tentativas_imagem": 3,
    "tempo_inicio": 2,
    "failsafe_ativo": True,
    "intervalo_digitacao": 0.05,
    "intervalo_digitacao_variavel": False,
    "pausa_entre_acoes": 0.1,
    "pausa_entre_acoes_variavel": False,
    "imagem_cinza": True,
}


def _projeto_repetido():
    p = projeto.Projeto("fluxo teste")
    p.adicionar("clicar", x=100, y=200, cliques=2)
    p.adicionar("bloco_inicio", vezes=3)
    p.adicionar("digitar", texto="linha '1'\nlinha 2")
    p.adicionar("tecla", nome="enter")
    p.adicionar("bloco_fim")
    p.adicionar("imagem_clicar", arquivo="btn.png", timeout=7, confianca=0.8,
                offset=[5, -3], fallback=[10, 20])
    p.adicionar("imagem_esperar", arquivo="ok.png", se_falhar="continuar")
    p.adicionar("imagem_desaparecer", arquivo="load.png")
    p.config["repeticoes"] = 2
    return p


def test_codigo_compila_e_tem_loops():
    fonte = codegen.gerar_codigo(_projeto_repetido(), CFG)
    compile(fonte, "gerado.py", "exec")
    assert "for _ in range(3):" in fonte
    assert "for i in range(1, 2 + 1):" in fonte
    assert "timeout=7" in fonte
    assert "_dividir_texto" in fonte
    assert "confidence=0.8" in fonte
    assert "fallback=(10, 20)" in fonte
    assert "obrigatorio=False" in fonte
    assert "_parar.set()" in fonte  # ESC de verdade, sem sys.exit em thread
    assert "os._exit" not in fonte


def test_repeticao_infinita():
    p = projeto.Projeto()
    p.adicionar("pausa", segundos=1)
    p.config["repeticoes"] = 0
    fonte = codegen.gerar_codigo(p, CFG)
    compile(fonte, "gerado.py", "exec")
    assert "while True:" in fonte
    assert "infinito" in fonte


def test_bloco_vazio_nao_quebra():
    p = projeto.Projeto()
    p.adicionar("bloco_inicio", vezes=2)
    p.adicionar("bloco_fim")
    p.adicionar("pausa", segundos=1)
    fonte = codegen.gerar_codigo(p, CFG)
    compile(fonte, "gerado.py", "exec")
    assert "pass" in fonte


def test_exportar_sidecar(tmp_path, imagens_tmp):
    from PIL import Image

    imagem = Image.new("RGB", (10, 10), "white")
    imagem.save(imagens_tmp / "btn.png")
    p = projeto.Projeto("export")
    p.adicionar("imagem_clicar", arquivo="btn.png")
    info = codegen.exportar(p, tmp_path / "saida" / "script.py", CFG)
    assert info["script"].exists()
    assert info["sidecar"].exists()
    dados = json.loads(info["sidecar"].read_text(encoding="utf-8"))
    assert dados["nome"] == "export"
    assert (tmp_path / "saida" / "imagens_templates" / "btn.png").exists()
    compile(info["script"].read_text(encoding="utf-8"), "s.py", "exec")


def test_exportar_sem_pasta_de_saida_cria(tmp_path):
    p = projeto.Projeto("vazio")
    p.adicionar("pausa", segundos=0.5)
    info = codegen.exportar(p, tmp_path / "a" / "b" / "x.py", CFG)
    assert info["script"].parent.exists()


def test_runtime_gerado_divide_tokens_de_texto():
    import ast
    import re

    fonte = codegen.gerar_codigo(_projeto_repetido(), CFG)
    corpo = ast.parse(fonte).body
    inicio = next(
        i
        for i, no in enumerate(corpo)
        if isinstance(no, ast.Assign)
        and isinstance(no.targets[0], ast.Name)
        and no.targets[0].id == "_ALIAS_TECLAS"
    )
    fim = next(
        i
        for i, no in enumerate(corpo)
        if isinstance(no, ast.FunctionDef) and no.name == "_dividir_texto"
    )
    espaco = {"re": re}
    exec(
        compile(
            ast.Module(body=corpo[inicio : fim + 1], type_ignores=[]),
            "<runtime>",
            "exec",
        ),
        espaco,
    )
    dividir = espaco["_dividir_texto"]
    assert dividir("a{ENTER}b") == [
        ("texto", "a"),
        ("tecla", "enter"),
        ("texto", "b"),
    ]
    assert dividir("{foo}") == [("texto", "{foo}")]
