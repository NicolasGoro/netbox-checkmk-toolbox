import sys
from pathlib import Path
import paramiko

# --- CONFIGURAZIONE ---
REMOTE_HOST = "192.168.204.131"
REMOTE_USER = "automation"
REMOTE_KEY_PATH = str(Path.home() / "Documents" / "Chiavi" / "chiave_privata")

# --- NETBOX ---
REMOTE_DIR = "/home/automation/netbox-checkmk-toolbox/import_netbox"
REMOTE_SCRIPT = "netbox_data_loader.py"

# --- CHECKMK ---
CHECKMK_DIR = "/home/automation/netbox-checkmk-toolbox/checkmk_integration"
CHECKMK_SCRIPT = "cmk_nbox_push.py"

def find_excel_file() -> Path:
    """
    Cerca i file .xlsx sulla scrivania dell'utente locale.

    Comportamento:
        - Nessun file trovato -> genera un errore.
        - Un solo file trovato -> lo restituisce direttamente, senza chiedere la conferma.
        - Più file trovati -> apre una finestra di dialogo su Pycharm che consente la scelta del file.
    """

    # Path.home() restituisce la home directory dell'utente corrente (es. /Users/Nicolas.Gorini su Mac)
    desktop = Path.home() / "Desktop"

    # glob("*.xlsx") cerca tutti i file con estensione .xlsx nel percorso selezionato, generando una lista
    excel_files = list(desktop.glob("*.xlsx"))

    #Se la lista è vupta interrompe direttamente lo script.
    if not excel_files:
        raise FileNotFoundError("Nessun file .xlsx trovato sulla scrivania")

    # Se è presente solo un file viene utilizzato immediatamente
    if len(excel_files) == 1:
        return excel_files[0]

    # Se sono presenti più file genera un elenco che permette la scelta d1a CLI PyCharm
    print(f"Trovati {len(excel_files)} file .xlsx sulla scrivania:")

    # enumerate(..., start=1) numera le voci a partire da 1 (più naturale
    for i, f in enumerate(excel_files, start=1):
        print(f"  {i}. {f.name}")

    # input() sospende lo script in attesa che l'utente digiti qualcosa
    scelta = input("Inserisci il numero del file da caricare (o Invio per annullare): ").strip()

    # Se l'utente preme solo Invio senza digitare nulla, l'operazione viene annullata.
    if not scelta:
        raise FileNotFoundError("Nessun file selezionato: operazione annullata")

    try:
        # Convertiamo la stringa digitata in un numero intero e la traduciamo
        # Nell'indice della lista (che parte da 0, per questo il -1).
        indice = int(scelta) - 1
        if indice < 0:
            raise IndexError  # forziamo la stessa gestione degli indici fuori range
        return excel_files[indice]
    except ValueError:
        # int() solleva ValueError se l'utente ha digitato qualcosa che
        # Non è un numero (es. lettere).
        raise ValueError(f"'{scelta}' non è un numero valido")
    except IndexError:
        # La lista non ha un elemento a quell'indice (numero troppo alto o troppo basso).
        raise IndexError(f"Numero '{scelta}' non valido: scegli un valore tra 1 e {len(excel_files)}")


def esegui_comando_remoto_streaming(ssh: paramiko.SSHClient, cmd: str) -> int:
    """
    Esegue un comando sulla macchina remota e stampa il suo Output RIGA per RIGA.
    """
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)

    # Il "channel" è il canale di comunicazione di basso livello sottostante
    # a stdout/stderr: ci permette di controllare se ci sono dati pronti
    # da leggere SENZA bloccare l'esecuzione in attesa che il comando finisca.
    channel = stdout.channel

    # Ciclo che continua finché non abbiamo letto tutto l'output disponibile
    while True:
        # recv_ready() è non bloccante: ci dice "ci sono byte pronti adesso" senza fermare lo script in attesa.
        if channel.recv_ready():
            output = channel.recv(4096).decode(errors="replace")
            # end="" evita di aggiungere un newline extra (l'output remoto
            # contiene già i propri \n), flush=True forza la stampa immediata
            # invece di aspettare che il buffer di stampa si riempia.
            print(output, end="", flush=True)

        # Controlliamo anche il canale stderr separato. Con get_pty=True
        # spesso stdout e stderr remoti finiscono mescolati sullo stesso
        # canale, ma controlliamo comunque stderr per sicurezza.
        if channel.recv_stderr_ready():
            err_output = channel.recv_stderr(4096).decode(errors="replace")
            print(err_output, end="", flush=True)

        # exit_status_ready() diventa True quando il comando remoto è terminato.
        # Usciamo dal ciclo solo se il comando è finito E non ci sono più dati
        # residui da leggere, per non perdere le ultime righe di output.
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break

    # Recupera il codice di uscita effettivo del comando remoto
    # (0 = successo, diverso da 0 = errore).
    exit_status = channel.recv_exit_status()
    return exit_status

def chiedi_conferma(domanda: str) -> bool:
    """
    Chiede una conferma sì/no da terminale.

    Argomenti:
        domanda: il testo da mostrare all'utente (senza "[s/n]", lo aggiunge
                  già questa funzione).

    Restituisce:
        bool: True se l'utente ha risposto "s"/"si"/"y"/"yes", False altrimenti
              (compreso il caso in cui prema solo Invio, per sicurezza).
    """
    # input() blocca l'esecuzione finché l'utente non digita e preme Invio.
    # .strip() rimuove eventuali spazi accidentali,.lower() rende il
    # confronto insensibile a maiuscole/minuscole (es. "S", "s", "Si" vanno bene tutti).
    risposta = input(f"{domanda} [s/N]: ").strip().lower()
    return risposta in ("s", "si", "sì", "y", "yes")

def chiedi_tenant(nome_suggerito: str) -> str:
    """
    Chiede all'utente di digitare esplicitamente il nome del Tenant da
    sincronizzare con Checkmk.

    Argomenti:
        nome_suggerito: il nome del file Excel (senza estensione), mostrato come suggerimento/default.

    Restituisce:
        str: il nome del Tenant scelto dall'utente. Se preme solo Invio, viene usato il nome suggerito.
    """

    risposta = input(f"Nome del Tenant da sincronizzare con Checkmk [{nome_suggerito}]: ").strip()

    # Se l'utente non digita nulla e preme solo Invio, usiamo il suggerimento;
    # altrimenti usiamo esattamente quello che ha digitato.
    return risposta if risposta else nome_suggerito

def main():
    # 1. TROVA (O FA SCEGLIERE) IL FILE LOCALE
    local_file = find_excel_file()
    print(f"File selezionato: {local_file}")

    # 2. APRE LA CONNESSIONE SSH
    # SSHClient è l'oggetto principale di paramiko che gestisce la connessione
    # SSH (autenticazione, esecuzione comandi, trasferimento file via SFTP).
    ssh = paramiko.SSHClient()

    # Di default, paramiko rifiuta di connettersi a host la cui "impronta" (host key) non è già conosciuta, per motivi
    # di sicurezza (protezione da attacchi man-in-the-middle). AutoAddPolicy() dice a paramiko di accettare e salvare
    # automaticamente qualsiasi host key incontrata.
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Stabilisce la connessione SSH vera e propria, autenticandosi con la chiave privata invece che con una password.
    ssh.connect(REMOTE_HOST, username=REMOTE_USER, key_filename=REMOTE_KEY_PATH)

    # Costruisce il path completo di destinazione sulla macchina remota, combinando la cartella di lavoro.
    remote_path = f"{REMOTE_DIR}/{local_file.name}"

    # 3. CARICA IL FILE VIA SFTP
    # aperto: open_sftp() apre un sotto-canale dedicato al trasferimento file.
    sftp = ssh.open_sftp()
    print(f"Carico {local_file.name} su {remote_path} ...")

    # .put(sorgente_locale, destinazione_remota) copia il file dalla tua macchina alla macchina remota. str(local_file).
    # Path in una stringa, richiesta dall'API di paramiko.
    sftp.put(str(local_file), remote_path)

    # Chiude il canale SFTP: il file è già stato trasferito, non serve più.
    sftp.close()

    # 4. ESEGUE IL COMANDO REMOTO CON OUTPUT IN TEMPO REALE
    # Costruiamo la stringa di comando come se la digitassi a mano in una shell:
    # entriamo nella cartella (cd) e lanciamo lo script Python passando
    # come argomento il nome del file appena caricato.
    cmd = f"cd {REMOTE_DIR} && python3 {REMOTE_SCRIPT} {local_file.name}"
    print(f"Eseguo: {cmd}")
    print("--- OUTPUT IN TEMPO REALE ---")

    # Al posto di exec_command + recv_exit_status "secco", usiamo la funzione
    # di streaming definita sopra: stampa l'output man mano che arriva,
    # invece di aspettare la fine dell'esecuzione per vederlo tutto insieme.
    exit_status = esegui_comando_remoto_streaming(ssh, cmd)

    # 5. GESTIONE DELL'ESITO DELL'IMPORT SU NETBOX
    # Se il comando remoto è terminato con un codice diverso da 0,
    # interrompiamo qui: non ha senso proseguire con pulizia file e
    # sincronizzazione Checkmk se l'import stesso è fallito.
    if exit_status != 0:
        print(f"\nComando terminato con errore (exit code {exit_status})")
        ssh.close()
        sys.exit(exit_status)

    print("\nImport completato con successo")

    # 6. RIMOZIONE DEL FILE EXCEL DALLA MACCHINA REMOTA
    # Eseguita SOLO se l'import è andato a buon fine (siamo qui solo in quel caso,
    # grazie al controllo sull'exit_status appena sopra). Usiamo di nuovo SFTP,
    # stavolta con il metodo.remove() invece di .put().
    print(f"Rimuovo {remote_path} dalla macchina remota...")
    sftp = ssh.open_sftp()
    try:
        sftp.remove(remote_path)
        print("File rimosso correttamente")
    except IOError as e:
        # Non blocchiamo lo script per un errore di pulizia: l'import è già
        # andato a buon fine, la mancata rimozione è un problema minore
        # (es. permessi) che segnaliamo ma non impedisce di proseguire.
        print(f"Attenzione: impossibile rimuovere il file remoto ({e})")
    finally:
        sftp.close()

    # 7. SINCRONIZZAZIONE CON CHECKMK (CON CONFERMA)
    # Il nome del Tenant NON viene più assunto automaticamente uguale al nome
    # del file Excel (i due possono non combaciare): chiediamo all'utente di
    # digitarlo esplicitamente, suggerendo però il nome del file come default
    # comodo per il caso più comune in cui i due nomi coincidono davvero.
    tenant = chiedi_tenant(nome_suggerito=local_file.stem)

    if chiedi_conferma(f"Vuoi sincronizzare il Tenant '{tenant}' con Checkmk?"):
        cmd_checkmk = f"cd {CHECKMK_DIR} && python3 {CHECKMK_SCRIPT} {tenant}"
        print(f"Eseguo: {cmd_checkmk}")
        print("--- OUTPUT IN TEMPO REALE ---")

        exit_status_checkmk = esegui_comando_remoto_streaming(ssh, cmd_checkmk)

        if exit_status_checkmk != 0:
            print(f"\nSincronizzazione Checkmk terminata con errore (exit code {exit_status_checkmk})")
            ssh.close()
            sys.exit(exit_status_checkmk)
        else:
            print("\nSincronizzazione Checkmk completata con successo")
    else:
        print("Sincronizzazione Checkmk saltata su richiesta dell'utente")

    # Chiude la connessione SSH principale, liberando la risorsa.
    ssh.close()

# Questo blocco fa sì che main() venga eseguito SOLO quando il file è lanciato
# direttamente (es. python3 push_to_netbox_and_checkmk.py), e NON quando viene importato
# come modulo da un altro script Python.
if __name__ == "__main__":
    main()
