# Cookies: aceitar JSON + mensagens de erro específicas

## Mudanças em `src/inemadlp/cookies.py`

1. **Aceita o export JSON da extensão** (`Get cookies.txt LOCALLY` e similares):
   - Detecta JSON quando o conteúdo (após strip) começa com `[` ou `{`.
   - `_converter_json` faz o parse e aceita tanto um array top-level de cookies
     quanto `{"cookies": [...]}`.
   - `_cookie_dict_para_linha` lê tolerantemente `domain`, `name`, `value`,
     `path` (default `/`), `secure`, `httpOnly`/`httponly`, e a expiração em
     `expirationDate`/`expires`/`expiry` (float ou int, ausente = sessão = `0`
     via `_expiry_para_netscape`). Emite `#HttpOnly_` como prefixo de domínio
     quando `httpOnly` é verdadeiro, e o `domain_specified` a partir do ponto
     inicial do domínio.
   - Gera o cabeçalho `# Netscape HTTP Cookie File` e entrega o texto Netscape
     resultante para o pipeline existente (`_sanitizar` + validação com
     `YoutubeDLCookieJar`) — a garantia de aceitação continua sendo "o yt-dlp
     consegue carregar".

2. **Mensagens de rejeição específicas, em português, com o próximo passo**:
   - conteúdo vazio/só espaço → "o arquivo enviado está vazio...";
   - JSON malformado → menciona "JSON" e orienta exportar como `cookies.txt`;
   - JSON parseado mas sem `cookies` usável (array vazio, chave errada, nenhum
     objeto com domain/name/value) → mensagens dedicadas;
   - HTML (`<...`) → menciona "HTML" e explica que a página foi salva por
     engano em vez do export da extensão;
   - cabeçalho Netscape ausente → mensagem original, mantida;
   - campos separados por ESPAÇO em vez de TAB → `_campos_separados_por_espaco`
     detecta linhas sem tab que têm exatamente 7 tokens separados por espaço, e
     a mensagem menciona "TAB" explicitamente;
   - todas as linhas descartadas → agora informa quantas linhas foram
     examinadas;
   - arquivo carregado mas zero cookies úteis → coberto pelo mesmo caminho
     acima (contagem de linhas úteis == 0).

Tudo o mais foi mantido: escrita atômica (tmp + `os.replace`), upload rejeitado
não toca no `cookies.txt` anterior, o shape de `SaveResult`
(`cookies`/`corrigidos`/`descartados`) e a API que o consome.

## Testes (`tests/test_cookies.py`)

Adicionados 7 testes novos, todos falhando antes da mudança:
- `test_save_accepts_json_array_export` — array JSON realista (httpOnly misto,
  `expirationDate` float, cookie de sessão sem expiração) é aceito e carrega no
  `YoutubeDLCookieJar` com os nomes esperados.
- `test_save_accepts_json_object_with_cookies_key` — wrapper `{"cookies": [...]}`.
- `test_save_rejects_malformed_json` — JSON quebrado levanta `InvalidCookieFile`
  com "JSON" na mensagem.
- `test_save_rejects_html_page` — HTML levanta erro mencionando "HTML".
- `test_save_rejects_space_separated_fields` — campos separados por espaço
  levanta erro mencionando "TAB".
- `test_save_rejects_empty_content` — conteúdo vazio levanta erro mencionando
  "vazio".
- (os testes existentes de cabeçalho, escrita atômica e reparo do caso msn.com
  continuam intactos e passando)

## README.md

Seção "Cookies" atualizada: menciona que tanto `cookies.txt` (Netscape) quanto
o export JSON são aceitos, recomenda `cookies.txt` quando a extensão oferecer
escolha, e nota que as mensagens de erro agora explicam o motivo da rejeição.

## Testes: resultado real

```
90 passed, 1 deselected, 1 warning in 1.88s
```
