# 🚀 Guia de Publicação na Nuvem: ARPego (Render.com)

Este guia explica como publicar o seu assistente na nuvem gratuita do **Render.com** para obter o endereço público:
👉 **`https://arpego.onrender.com`**

---

## 🛠️ Passo 1: Criar Repositório no GitHub (ou GitLab)
1. Acesse [github.com](https://github.com) e crie um novo repositório (pode ser Privado ou Público) com o nome: **`arpego`**.
2. Faça upload dos arquivos desta pasta `AssistentePessoal` para o repositório:
   - `app.py`
   - `painel.html`
   - `Procfile`
   - `requirements.txt`
   - `render.yaml`

---

## ☁️ Passo 2: Publicar Gratuitamente no Render.com
1. Acesse [render.com](https://render.com) e crie uma conta gratuita (pode entrar com sua conta do GitHub ou Google).
2. No painel, clique em **New +** e escolha **Web Service**.
3. Conecte o seu repositório **`arpego`**.
4. Nas configurações do serviço:
   - **Name:** `arpego`
   - **Environment:** `Python`
   - **Build Command:** *(deixe em branco ou `pip install -r requirements.txt`)*
   - **Start Command:** `python app.py`
   - **Instance Type:** `Free` (Gratuito)
5. Clique em **Create Web Service**.

---

## 📱 Passo 3: Acessar pelo Celular de Qualquer Lugar
Em cerca de 1 a 2 minutos, o Render gerará o link seguro:
👉 **`https://arpego.onrender.com`**

* Funciona no 4G, 5G ou em qualquer Wi-Fi;
* Não depende do seu notebook estar ligado;
* No celular, toque em **Adicionar à tela inicial** para ter seu app definitivo!
