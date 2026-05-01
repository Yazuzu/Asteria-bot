# 🔥 Astéria-bot

Um **Discord bot conversacional** com IA que implementa uma personalidade única: **Astéria** — extrovertida, provocadora, estratégica e impulsiva.

## 🎯 Visão Geral

Astéria é um bot experimental que combina:
- **Large Language Model** (Llama 3 via KoboldCPP local)
- **Sistema de memória avançado** (LanceDB + Density Matrix)
- **Análise emocional** (Go-Emotion distilbert)
- **Two-Call Strategy** (PersonaReAct para análise contextual + resposta)
- **Detecção de perfil de usuário** (pattern matching leve)

### ✨ Características

✅ Conversas coerentes e contextualizadas  
✅ Memória persistente por canal  
✅ Análise de emoção do usuário  
✅ Adaptação de tom baseada em perfil  
✅ Suporte a roleplay (RP) com limite de tokens aumentado  
✅ Logging estruturado e métricas de performance  
✅ Cooldowns em comandos de diversão  

---

## 📋 Requisitos

- **Python 3.9+**
- **Discord Bot Token** (criar em [Developer Portal](https://discord.com/developers/applications))
- **KoboldCPP** rodando localmente (ou servidor remoto)
- **Modelos de IA** (baixados automaticamente via Hugging Face)

---

## 🚀 Instalação Rápida

### 1. Clone o repositório
```bash
git clone https://github.com/Yazuzu/Asteria-bot.git
cd Asteria-bot
```

### 2. Crie um ambiente virtual
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Instale dependências
```bash
pip install -r requirements.txt
```

### 4. Configure variáveis de ambiente
```bash
cp .env.example .env
# Edite .env com seus dados:
# - DISCORD_TOKEN
# - OWNER_IDS
# - KOBOLD_URL
```

### 5. Inicie KoboldCPP (em outro terminal)
```bash
# Assumindo KoboldCPP instalado
python -m koboldcpp --host 0.0.0.0 --port 5001 --model /path/to/model.gguf
```

### 6. Execute o bot
```bash
python main.py
```

---

## 🎮 Uso

### Interagir com Astéria

**Mencionar o bot:**
```
@Astéria Olá, como você está?
```

**Responder a mensagem anterior:**
Faça reply à mensagem anterior do bot

**DM direto:**
Envie uma mensagem privada para Astéria

**Roleplay (ação):**
```
*Astéria olha para você com curiosidade* Que quer?
```
> Astéria detecta `*` e adapta a resposta para RP (até 300 tokens)

### Comandos Disponíveis

| Comando | Aliases | Descrição |
|---------|---------|-----------|
| `!ajuda` | `!help` | Mostra lista de comandos |
| `!roll [lados]` | `!dado` | Rola um dado (padrão: d6) |
| `!coinflip` | `!moeda`, `!flip` | Joga uma moeda |
| `!escolha opt1 \| opt2 \| opt3` | `!choose` | Escolhe entre opções |
| `!limpar_memoria` | `!clear_memory` | Limpa contexto do canal |

---

## 🏗️ Arquitetura

```
┌─────────────────┐
│   Discord API   │
└────────┬────────┘
         │
    ┌────▼────────────────────────────┐
    │    main.py (Event Handler)       │
    │  - on_ready()                    │
    │  - on_message()                  │
    │  - handle_asteria_message()      │
    └────┬─────────────────────────────┘
         │
    ┌────▼────────────────────────────┐
    │  asteria_conversation.py         │
    │  - process_message()             │
    │  - _get_context_with_confidence()│
    │  - _update_state()               │
    └────┬─────────────────────────────┘
         │
   ┌─────┴──────────────────────────────────────┐
   │                                              │
┌──▼──────────────────┐         ┌───────────────▼──┐
│ memory_system.py    │         │ persona_react_   │
│ - MemoryService     │         │ engine.py        │
│ - LanceDB storage   │         │ - Análise        │
│ - Embeddings        │         │ - Geração        │
│ - Emotions          │         │ - Métricas       │
└─────────────────────┘         └──────────────────��
         │                                │
    ┌────▼────────────────────────────────▼────┐
    │        llm_client.py (KoboldCPP)          │
    │  - generate(prompt, max_tokens, temp)    │
    └──────────────────────────────────────────┘
         │
    ┌────▼────────────────────────────────┐
    │   Llama 3 (Local via KoboldCPP)      │
    └─────────────────────────────────────┘
```

---

## ⚙️ Configuração Detalhada

### LLM (KoboldCPP)

**Parâmetros críticos:**
- `temperature`: Criatividade (0.7 recomendado)
- `repetition_penalty`: Evita repetições (1.15 recomendado)
- `top_p`: Núcleo de amostragem (0.95)
- `stop_tokens`: Marcadores de parada

### Memória

**Dois níveis:**
1. **L1 (recente):** Últimas 6 mensagens por canal em JSON
2. **L2 (longo prazo):** LanceDB com embeddings + Density Matrix

**Estratégia de reranking:**
- Similaridade semântica (embedding)
- Análise emocional (VAD: valência/arousal/dominância)
- Densidade de informação (matriz de densidade)

### PersonaReAct (Two-Call Strategy)

**Fase 1 - Análise (T=0.3):**
- Analisa mensagem com baixa temperatura
- Retorna: tom, estratégia, nível de escalação

**Fase 2 - Resposta (T=0.9):**
- Gera resposta criativa usando hints da Fase 1
- Mantém coerência com perfil detectado

---

## 📊 Arquivos Principais

| Arquivo | Função |
|---------|--------|
| `main.py` | Entry point, event handlers Discord |
| `config.py` | Carregamento de variáveis de ambiente |
| `asteria_conversation.py` | Orquestrador principal |
| `persona_react_engine.py` | Two-call LLM strategy |
| `memory_system.py` | LanceDB + embeddings + emoção |
| `memory.py` | Cache L1 simples (JSON) |
| `personality_system.py` | Detecção de perfil |
| `llm_client.py` | Cliente KoboldCPP |
| `prompts.py` | System prompt de Astéria |
| `cogs/fun.py` | Comandos de diversão |

---

## 🔧 Troubleshooting

### Bot não conecta ao Discord
```
❌ Error: DISCORD_TOKEN não definido
✅ Solução: Verifique .env e execute: python -c "from config import DISCORD_TOKEN; print(DISCORD_TOKEN)"
```

### KoboldCPP timeout
```
❌ Error: Timeout na requisição ao KoboldCPP
✅ Solução: Verifique se KoboldCPP está rodando em http://localhost:5001
```

### Modelo não encontrado
```
❌ Error: EmbeddingError ou transformers not found
✅ Solução: pip install --upgrade transformers sentence-transformers
```

### LanceDB locked
```
❌ Error: database is locked
✅ Solução: Feche outras instâncias do bot. LanceDB não suporta escrita concorrente.
```

---

## 📈 Monitoramento

### Logs
```bash
tail -f logs/asteria.log
```

**Níveis:**
- `INFO`: Eventos normais (login, mensagens processadas)
- `WARNING`: Problemas recuperáveis (timeout, parsing JSON falhou)
- `ERROR`: Problemas graves (token inválido, modelo não baixado)

### Métricas

Acessar stats de PersonaReAct:
```python
# Em qualquer cog ou command:
stats = bot.persona_engine.get_metrics_stats()
print(stats)
# {
#   "total": 1234,
#   "success_rate": 98.5,
#   "latency_avg_ms": 345.2,
#   "tone_distribution": {"aggressive": 450, "curious": 300, ...}
# }
```

---

## 🎯 Roadmap

- [ ] Múltiplas personalidades (não só Astéria)
- [ ] Dashboard web de monitoramento
- [ ] Integração com Mem0 (advanced memory)
- [ ] Suporte a slash commands
- [ ] Testes unitários e E2E
- [ ] Docker setup
- [ ] Support para modelos remotos (API)

---

## ⚠️ Limitações & Considerações

1. **Local Only:** Requer KoboldCPP rodando localmente (pode ser remoto via KOBOLD_URL)
2. **Modelos Pesados:** Embedding + Emotion = ~1GB RAM
3. **Sem Suporte Nativo a Threads:** Use canais normais
4. **Rate Limiting:** Implemente via Discord's native limits
5. **Persistência:** Memória é persistida em `data/` e `logs/`

---

## 📝 Licença

MIT (você é livre para modificar e usar)

---

## 💬 Suporte

**Problemas?**
- Cheque os logs em `logs/asteria.log`
- Ative `ENABLE_PERF_LOGGING=True` para debug
- Veja a seção **Troubleshooting** acima

---

## 👤 Autor

**Yazuzu** — Criador e mantedor do Astéria-bot

---

**Última atualização:** 2026-05-01  
**Status:** Em desenvolvimento ativo
