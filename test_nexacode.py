"""Testes ponta a ponta do Nexacode (Playwright + provedores simulados). Uso: python3 test_nexacode.py caminho/index.html"""
import sys, json, traceback
from playwright.sync_api import sync_playwright
import mock
F = "file://" + (sys.argv[1] if len(sys.argv) > 1 else "/home/claude/t/new_index.html")
R = []
def teste(f):
    try: f(); R.append((f.__name__, True, ""))
    except Exception as e: R.append((f.__name__, False, (str(e).splitlines() or [repr(e)])[0][:160]))
    return f
def novo(b, keys=(), beh=None, mode="economia", w=1100, h=800, pend=None, log=None):
    pg = b.new_page(viewport={"width": w, "height": h}); mock.install(pg, beh or {}, pend, log)
    if keys: mock.seed(pg, keys, mode)
    pg.on("dialog", lambda d: d.accept("Título novo") if d.type == "prompt" else d.accept())
    pg.goto(F); return pg
def enviar(pg, txt):
    pg.fill("#t", txt); pg.click("#go")
def resp(pg): pg.wait_for_selector(".m.a .meta", timeout=8000); return pg.inner_text(".m.a")
with sync_playwright() as p:
    b = p.chromium.launch()
    @teste
    def tela_inicial_sem_chave():
        pg = novo(b); assert "Adicionar chave API" in pg.inner_text(".hi .pill"); pg.click(".hi .pill"); assert pg.is_visible("#dk")
    @teste
    def adicionar_chave_pela_interface():
        pg = novo(b); pg.click(".hi .pill"); pg.click("#padd .chip:has-text('Groq')"); pg.fill("#pform input", "gsk_" + "a" * 30); pg.click("#pform .pill")
        pg.wait_for_selector("#pcards .card"); cfg = pg.evaluate("JSON.parse(localStorage.nx_cfg)")
        assert "groq" in cfg["keys"] and cfg["status"]["groq"]["ok"] == 1 and cfg["models"]["groq"] == "llama-3.3-70b-x"
    @teste
    def chave_de_outro_provedor_e_rejeitada():
        pg = novo(b); pg.click(".hi .pill"); pg.click("#padd .chip:has-text('Gemini')"); pg.fill("#pform input", "gsk_" + "a" * 30); pg.click("#pform .pill")
        assert "parece ser de Groq" in pg.inner_text("#pform"); assert pg.evaluate("!localStorage.nx_cfg||!JSON.parse(localStorage.nx_cfg).keys.gemini")
    @teste
    def remover_uma_e_todas_as_chaves():
        pg = novo(b, ["groq", "gemini"]); pg.click("#bk"); assert pg.locator("#pcards .card").count() == 2
        pg.click("#pcards .card >> nth=0 >> button[title^='Remover']"); assert pg.locator("#pcards .card").count() == 1
        pg.click("#rmall"); assert pg.locator("#pcards .card").count() == 0 and pg.evaluate("Object.keys(JSON.parse(localStorage.nx_cfg).keys).length") == 0
    @teste
    def economia_troca_de_provedor_no_429():
        pg = novo(b, ["groq", "gemini"], {"api.groq.com": "429"}); enviar(pg, "olá mundo"); t = resp(pg)
        assert "resp-generativelanguage" in t and "gemini" in t
        assert pg.evaluate("JSON.parse(localStorage.nx_use).groq.until>Date.now()")
    @teste
    def resposta_vazia_cai_para_o_proximo():
        pg = novo(b, ["groq", "gemini"], {"api.groq.com": "empty"}); enviar(pg, "teste vazio"); assert "resp-generativelanguage" in resp(pg)
    @teste
    def fusao_usa_duas_ias_e_um_juiz():
        pg = novo(b, ["groq", "gemini"], mode="fusao"); enviar(pg, "analise e compare duas coisas"); t = resp(pg)
        assert "fusao" in t and "groq" in t and "gemini" in t, t
    @teste
    def fusao_com_uma_ia_e_honesta():
        pg = novo(b, ["groq"], mode="fusao"); enviar(pg, "analise e compare duas coisas"); t = resp(pg); assert "economia (só 1 IA ativa)" in t, t
    @teste
    def critica_com_duas_ias():
        pg = novo(b, ["groq", "gemini"], mode="critica"); enviar(pg, "escreva um poema curto"); t = resp(pg); assert "critica" in t and "groq" in t and "gemini" in t, t
    @teste
    def corrida_devolve_uma_resposta():
        pg = novo(b, ["groq", "gemini"], {"api.groq.com": "hang"}, mode="corrida", pend=[]); enviar(pg, "pergunta rápida de teste"); t = resp(pg); assert "resp-generativelanguage" in t, t
    @teste
    def cancelar_nao_deixa_mensagem_orfa():
        pg = novo(b, ["groq"], {"api.groq.com": "hang"}, pend=[]); enviar(pg, "vai cancelar"); pg.wait_for_timeout(300); pg.click("#go"); pg.wait_for_timeout(300)
        assert pg.locator(".m.u").count() == 0 and pg.input_value("#t") == "vai cancelar" and pg.evaluate("(JSON.parse(localStorage.nx_cv||'[]')[0]||{msgs:[]}).msgs.length") == 0
    @teste
    def erro_total_mostra_erro_e_devolve_texto():
        pg = novo(b, ["groq", "gemini"], {"api.groq.com": "429", "generativelanguage.googleapis.com": "429"}); enviar(pg, "vai falhar"); pg.wait_for_selector(".m.err")
        assert pg.locator(".m.u").count() == 0 and pg.input_value("#t") == "vai falhar"
    @teste
    def resposta_cortada_e_avisada():
        pg = novo(b, ["groq"], {"api.groq.com": "cut"}); enviar(pg, "resposta longa"); assert "cortada pelo limite" in resp(pg)
    @teste
    def conversa_persiste_ao_recarregar():
        pg = novo(b, ["groq"]); enviar(pg, "guarde isto"); resp(pg); pg.reload(); pg.wait_for_selector(".m.a"); assert pg.locator(".m.u").count() == 1 and "guarde isto" in pg.inner_text(".m.u")
    @teste
    def xss_em_resposta_e_neutralizado():
        pg = novo(b, ["groq"], {"api.groq.com": "xss"}); enviar(pg, "xss"); t = resp(pg)
        assert pg.evaluate("window.__x") is None and pg.locator("#msgs img").count() == 0 and "texto seguro" in t
    @teste
    def exportar_nao_vaza_chave():
        pg = novo(b, ["groq"]); enviar(pg, "exporte"); resp(pg)
        with pg.expect_download() as d: pg.click("#ex")
        txt = open(d.value.path(), encoding="utf-8").read(); assert "Você" in txt and "exporte" in txt and "kkkkk" not in txt
    @teste
    def csp_bloqueia_destino_desconhecido():
        pg = novo(b); assert pg.evaluate("!!document.querySelector('meta[http-equiv=\"Content-Security-Policy\"]')")
        v = pg.evaluate("new Promise(r=>{document.addEventListener('securitypolicyviolation',e=>r(e.violatedDirective));fetch('https://evil.example.com/x').catch(()=>{})})")
        assert v.startswith("connect-src"), v
    @teste
    def historico_buscar_renomear_fixar_excluir():
        pg = novo(b, ["groq"]); enviar(pg, "primeira conversa sobre gatos"); resp(pg); pg.click("#nw"); enviar(pg, "segunda sobre carros"); pg.wait_for_selector(".m.a .meta"); pg.wait_for_timeout(300)
        pg.fill("#q", "gatos"); assert pg.locator(".cv").count() == 1; pg.fill("#q", "")
        pg.click(".cv.on button[title='Renomear']"); assert "Título novo" in pg.inner_text("#list")
        pg.click(".cv.on button[title='Fixar']"); assert "Fixadas" in pg.inner_text("#list")
        pg.click(".cv.on button[title='Excluir']"); assert pg.locator(".cv").count() == 1
    @teste
    def tema_persiste():
        pg = novo(b); a = pg.evaluate("document.documentElement.dataset.theme"); pg.click("#th"); n = pg.evaluate("document.documentElement.dataset.theme"); pg.reload()
        assert a != n and pg.evaluate("document.documentElement.dataset.theme") == n
    @teste
    def celular_sem_rolagem_horizontal_e_menu():
        pg = novo(b, ["groq"], w=360, h=740); enviar(pg, "teste no celular"); resp(pg)
        assert pg.evaluate("document.documentElement.scrollWidth<=innerWidth") and pg.evaluate("document.querySelector('#sb').getBoundingClientRect().right<=0")
        pg.click("#bm"); pg.wait_for_timeout(300); assert pg.evaluate("document.querySelector('#sb').getBoundingClientRect().left>=0")
        box = pg.evaluate("(()=>{const r=document.querySelector('.cmp').getBoundingClientRect();return [r.bottom,innerHeight]})()"); assert box[0] <= box[1] + 1
    @teste
    def alvo_de_toque_minimo_no_celular():
        pg = novo(b, ["groq"], w=360, h=740); s = pg.evaluate("[...document.querySelectorAll('#go,#bm,#th,#ex')].map(e=>Math.min(e.getBoundingClientRect().width,e.getBoundingClientRect().height))")
        assert min(s) >= 34, s
    b.close()
ok = sum(1 for r in R if r[1])
for n, o, m in R: print(("PASSOU  " if o else "FALHOU  ") + n + ("" if o else "  -> " + m))
print(f"\n{ok}/{len(R)} testes aprovados")
