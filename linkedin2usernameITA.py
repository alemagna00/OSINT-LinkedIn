#!/usr/bin/env python3

"""
linkedin2username tramite LeZavorre (github.com/alemagna00)

Strumento OSINT per scoprire probabili nomi utente e indirizzi e-mail per i dipendenti
di una determinata azienda su LinkedIn. Questo strumento effettivamente accede con il tuo file valid
conto per estrarre il maggior numero di risultati
"""

import os
import sys
import re
import time
import argparse
import json
import urllib.parse
import requests
import urllib3

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

LINKEDIN_USERNAME = "agnelloclaudio0@gmail.com"
LINKEDIN_PASSWORD = "NomeCognome123"

BANNER = r"""

                         _                     ______             
                        | |                   |  ____|            
                        | |    _   _  ___ __ _| |__   _ __   __ _ 
                        | |   | | | |/ __/ _` |  __| | '_ \ / _` |
                        | |___| |_| | (_| (_| | |____| | | | (_| |
                        |______\__,_|\___\__,_|______|_| |_|\__,_|
                                          
                                    github.com/alemagna00

"""

# Il dizionario seguente contiene i codici delle regioni geografiche. Poiché siamo limitati a 1000 risultati per ricerca,
# possiamo usarlo per effettuare ricerche in batch tra regioni e ottenere più risultati.
# https://static.licdn.com/aero-v1/sc/h/6pw526ylxpzsa7nu7ht18bo8y
GEO_REGIONS = {
    "ar": "100446943",
    "at": "103883259",
    "au": "101452733",
    "be": "100565514",
    "bg": "105333783",
    "ca": "101174742",
    "ch": "106693272",
    "cl": "104621616",
    "de": "101282230",
    "dk": "104514075",
    "es": "105646813",
    "fi": "100456013",
    "fo": "104630756",
    "fr": "105015875",
    "gb": "101165590",
    "gf": "105001561",
    "gp": "104232339",
    "gr": "104677530",
    "gu": "107006862",
    "hr": "104688944",
    "hu": "100288700",
    "is": "105238872",
    "it": "103350119",
    "li": "100878084",
    "lu": "104042105",
    "mq": "103091690",
    "nl": "102890719",
    "no": "103819153",
    "nz": "105490917",
    "pe": "102927786",
    "pl": "105072130",
    "pr": "105245958",
    "pt": "100364837",
    "py": "104065273",
    "re": "104265812",
    "rs": "101855366",
    "ru": "101728296",
    "se": "105117694",
    "sg": "102454443",
    "si": "106137034",
    "tw": "104187078",
    "ua": "102264497",
    "us": "103644278",
    "uy": "100867946",
    "ve": "101490751"
}

class NameMutator():
    """
    Questa classe gestisce tutte le mutazioni dei nomi.
    Init con un nome non elaborato, quindi chiama le singole funzioni per restituire una mutazione.
    """
    def __init__(self, name):
        self.name = self.clean_name(name)
        self.name = self.split_name(self.name)

    @staticmethod
    def clean_name(name):
        """
        Rimuove la punteggiatura comune.
        Gli utenti di LinkedIn tendono ad aggiungere credenziali ai loro nomi per sembrare speciali.
        Questa funzione si basa su ciò che ho visto in grandi ricerche e tentativi
        per rimuoverli.
        """
        # Tutto in minuscolo per facilitare la deduplicazione.
        name = name.lower()

        # Il caso d'uso dello strumento è principalmente l'inglese standard, provare a standardizzare il non inglese comune
        # caratteri.
        name = re.sub("[àáâãäå]", 'a', name)
        name = re.sub("[èéêë]", 'e', name)
        name = re.sub("[ìíîï]", 'i', name)
        name = re.sub("[òóôõö]", 'o', name)
        name = re.sub("[ùúûü]", 'u', name)
        name = re.sub("[ýÿ]", 'y', name)
        name = re.sub("[ß]", 'ss', name)
        name = re.sub("[ñ]", 'n', name)

        # Sbarazzarsi di tutte le cose tra parentesi. Molte persone mettono varie credenziali, ecc
        name = re.sub(r'\([^()]*\)', '', name)

        # Le righe sottostanti fondamentalmente spazzano via tutto ciò che è rimasto di strano.
        # Molti utenti hanno cose divertenti nei loro nomi, come () o ''
        # Alla gente piace sentirsi speciale, immagino.
        allowed_chars = re.compile('[^a-zA-Z -]')
        name = allowed_chars.sub('', name)

        # Successivamente, elimineremo i titoli comuni.
        titles = ['mr', 'miss', 'mrs', 'phd', 'prof', 'professor', 'md', 'dr', 'mba']
        pattern = "\\b(" + "|".join(titles) + ")\\b"
        name = re.sub(pattern, '', name)

        # La riga sottostante tenta di consolidare lo spazio bianco tra le parole
        # ed eliminare gli spazi iniziali/finali.
        name = re.sub(r'\s+', ' ', name).strip()

        return name

    @staticmethod
    def split_name(name):
        """
        Prende un nome (stringa) e restituisce un elenco di singole parti del nome (dict).
        Alcune persone hanno nomi divertenti. Supponiamo che i nomi più importanti siano:
        nome, cognome e il nome subito prima del cognome (se ne hanno uno)
        """
        parsed = re.split(' |-', name)

        # Scartare le persone senza almeno nome e cognome
        if len(parsed) < 2:
            return None

        if len(parsed) > 2:
            split_name = {'first': parsed[0], 'second': parsed[-2], 'last': parsed[-1]}
        else:
            split_name = {'first': parsed[0], 'second': '', 'last': parsed[-1]}

        return split_name

    """
    def f_last(self):
        -jsmith-
        names = set()
        names.add(self.name['first'][0] + self.name['last'])

        if self.name['second']:
            names.add(self.name['first'][0] + self.name['second'])

        return names
    """

    def f_dot_last(self):
        """j.smith"""
        names = set()
        names.add(self.name['first'][0] + '.' + self.name['last'])

        if self.name['second']:
            names.add(self.name['first'][0] + '.' + self.name['second'])

        return names

    """
    def last_f(self):
        -smithj-
        names = set()
        names.add(self.name['last'] + self.name['first'][0])

        if self.name['second']:
            names.add(self.name['second'] + self.name['first'][0])

        return names
    """

    def first_dot_last(self):
        """john.smith"""
        names = set()
        names.add(self.name['first'] + '.' + self.name['last'])

        if self.name['second']:
            names.add(self.name['first'] + '.' + self.name['second'])

        return names

    """
    def first_l(self):
        -johns-
        names = set()
        names.add(self.name['first'] + self.name['last'][0])

        if self.name['second']:
            names.add(self.name['first'] + self.name['second'][0])

        return names
    """

    """
    def first(self):
        -john-
        names = set()
        names.add(self.name['first'])

        return names
    """

def parse_arguments():
    """
    Gestire gli argomenti forniti dall'utente
    """
    desc = ('Strumento OSINT per generare elenchi di probabili nomi utente da un'
            ' data la pagina LinkedIn della azienda. Questo strumento potrebbe rompersi quando'
            ' LinkedIn cambia il proprio sito. Per favore apri i problemi su GitHub'
            'per segnalare eventuali incongruenze e verranno rapidamente risolte.')
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('-c', '--company', type=str, action='store',
                        required=True,
                        help='Il nome della azienda deve essere esattamente come e stato digitato nella società'
                        'URL della pagina del profilo LinkedIn.')
    parser.add_argument('-n', '--domain', type=str, action='store',
                        default='',
                        help='Aggiungi un nome di dominio all output del nome utente. '
                        '[esempio: "-n uber.com" restituirebbe jschmoe@uber.com]'
                        )
    parser.add_argument('-d', '--depth', type=int, action='store',
                        default=False,
                        help='Profondità di ricerca (quanti cicli di 50). Se non impostato, '
                        "cercherò di prenderli tutti.")
    parser.add_argument('-s', '--sleep', type=int, action='store', default=0,
                        help='Secondi per dormire tra un ciclo di ricerca e l altro.'
                        ' Il valore predefinito è 0.')
    parser.add_argument('-x', '--proxy', type=str, action='store',
                        default=False,
                        help='Server proxy da utilizzare. ATTENZIONE: SSL DISATTIVERA'
                        'VERIFICA. [esempio: "-p https://localhost:8080"]')
    parser.add_argument('-k', '--keywords', type=str, action='store',
                        default=False,
                        help='Filtra i risultati in base a un elenco di comandi separati '
                        'parole chiave. Eseguirà un ciclo separato per ciascuna parola chiave, '
                        'potenzialmente superando il limite di 1.000 record. '
                        '[esempio: "-k \'vendite,risorse umane,informazioni '
                        'tecnologia\']')
    parser.add_argument('-g', '--geoblast', default=False, action="store_true",
                        help='Tentativi di aggirare il limite di 1.000 ricerche di record'
                        'eseguendo più ricerche suddivise per area geografica regioni.')
    parser.add_argument('-o', '--output', default="li2u-output", action="store",
                        help='Directory di output, il valore predefinito è li2u-output')

    args = parser.parse_args()

    # L'argomento proxy viene fornito alle richieste come dizionario, impostandolo ora:
    args.proxy_dict = {"https": args.proxy}

    # Se aggiungi un indirizzo email, prepara questa stringa ora:
    if args.domain:
        args.domain = '@' + args.domain

    # Le parole chiave vengono inserite come elenco. Suddivisione ora dell'input utente separato da virgole:
    if args.keywords:
        args.keywords = args.keywords.split(',')

    # Queste due funzioni non sono attualmente compatibili, quindi lo schiacciamo ora:
    if args.keywords and args.geoblast:
        print("Spiacenti, al momento le parole chiave e geoblast non sono compatibili. Usa una o l'altra.")
        sys.exit()

    return args


def get_webdriver():
    """
    Prova a procurarti un driver del browser Selenium funzionante
    """
    for browser in [webdriver.Firefox, webdriver.Chrome]:
        try:
            return browser()
        except WebDriverException:
            continue
    return None

import getpass

def login():
    """
    Crea una nuova sessione autenticata.
    """
    driver = get_webdriver()

    if driver is None:
        print("[!] Impossibile trovare un browser supportato per Selenium. Uscita in corso.")
        sys.exit(1)

    driver.get("https://linkedin.com/login")

    # Attende fino a 10 secondi per il caricamento del campo di input per l'username
    username_field = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.NAME, "session_key")))

    # Inserisce le credenziali di accesso
    username_field.send_keys(LINKEDIN_USERNAME)

    password_field = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.NAME, "session_password")))
    password_field.send_keys(LINKEDIN_PASSWORD)
    password_field.send_keys(Keys.RETURN)

    # Pausa finché l'utente non ci informa che la sessione è valida
    print("[*] Accedi a LinkedIn. Lascia aperto il browser e premi Invio quando sei pronto...")
    input("Pronto? Premi Invio!")

    selenium_cookies = driver.get_cookies()
    driver.quit()

    # Inizializza e restituisce una sessione di richieste
    session = requests.Session()
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])

    # Aggiungi le intestazioni necessarie per il funzionamento di questo strumento
    mobile_agent = ('Mozilla/5.0 (Linux; U; Android 4.4.2; en-us; SCH-I535 '
                    'Build/KOT49H) AppleWebKit/534.30 (KHTML, like Gecko) '
                    'Version/4.0 Mobile Safari/534.30')
    session.headers.update({'User-Agent': mobile_agent,
                            'X-RestLi-Protocol-Version': '2.0.0',
                            'X-Li-Track': '{"clientVersion":"1.13.1665"}'})

    # Imposta il token CSRF
    session = set_csrf_token(session)

    return session

def set_csrf_token(session):
    """
    Estrai il token CSRF richiesto.
    Alcune funzioni richiedono un token CSRF uguale a JSESSIONID.
    """
    csrf_token = session.cookies['JSESSIONID'].replace('"', '')
    session.headers.update({'Csrf-Token': csrf_token})
    return session


def get_company_info(name, session):
    """
    Raschia informazioni aziendali di base.
    Tieni presente che non tutte le aziende inseriscono queste informazioni, quindi sono previste delle eccezioni.
    Il nome dell'azienda può essere trovato facilmente navigando su LinkedIn in un browser web,
    cercando l'azienda e guardando il nome nella barra degli indirizzi.
    """
    escaped_name = urllib.parse.quote_plus(name)

    response = session.get(('https://www.linkedin.com'
                            '/voyager/api/organization/companies?'
                            'q=universalName&universalName=' + escaped_name))

    if response.status_code == 404:
        print("[!] Impossibile trovare quel nome di azienda. Controlla attentamente su LinkedIn e riprova.")
        sys.exit()

    if response.status_code != 200:
        print("[!] Codice di risposta HTTP imprevisto durante il tentativo di ottenere informazioni sull'azienda:")
        print(f"    {response.status_code}")
        sys.exit()

    # Ad alcune regioni geografiche viene fornita una versione "lite" di LinkedIn mobile:
    #https://bit.ly/2vGcft0
    # La parte seguente è una soluzione temporanea finché non riesco a capire a
    # Soluzione a bassa manutenzione che include queste aree.
    if 'mwlite' in response.text:
        print("[!] Ti viene servita la versione 'lite' di"
              " LinkedIn (https://bit.ly/2vGcft0) che non è ancora supportato"
              "da questo strumento. Riprova utilizzando una VPN in uscita dagli Stati Uniti,"
              "Ue, o Australia.")
        print("    Si sta ricercando una soluzione permanente. Mi spiace!")
        sys.exit()

    try:
        response_json = json.loads(response.text)
    except json.decoder.JSONDecodeError:
        print("[!] Cavolo! Impossibile decodificare JSON durante la ricezione delle informazioni sull'azienda!")
        print("Ecco i primi 200 caratteri della risposta HTTP che possono aiutare nel debug:\n\n")
        print(response.text[:200])
        sys.exit()

    company = response_json["elements"][0]

    found_name = company.get('name', "NOT FOUND")
    found_desc = company.get('tagline', "NOT FOUND")
    found_staff = company['staffCount']
    found_website = company.get('companyPageUrl', "NOT FOUND")

    # Abbiamo bisogno dell'ID numerico per cercare informazioni sui dipendenti. Questo richiede alcune rifiniture
    # poiché è una porzione di stringa all'interno della chiave.
    # Esempio: "urn:li:company:1111111111" - ci serve 1111111111
    found_id = company['trackingInfo']['objectUrn'].split(':')[-1]

    print("          Name: " + found_name)
    print("          ID: " + found_id)
    print("          Desc:  " + found_desc)
    print("          Staff: " + str(found_staff))
    print("          URL:   " + found_website)
    print(f"\n[*] Speriamo che sia il giusto {name}! In caso contrario, controlla su LinkedIn e riprova.\n")

    return (found_id, found_staff)


def set_outer_loops(args):
    """
    Imposta il numero di loop da eseguire durante le sessioni di scraping
    """
    # Se utilizziamo geoblast o parole chiave, dobbiamo definire un numero di
    # "loop_esterni". Un ciclo esterno sarà una normale ricerca su LinkedIn, al massimo
    # su 1000 risultati.
    if args.geoblast:
        outer_loops = range(0, len(GEO_REGIONS))
    elif args.keywords:
        outer_loops = range(0, len(args.keywords))
    else:
        outer_loops = range(0, 1)

    return outer_loops


def set_inner_loops(staff_count, args):
    """
    Definisce i risultati totali nell'API di ricerca.

    Imposta un numero massimo di loop in base al numero di pentagrammi
    scoperto nella funzione get_company_info o nell'argomento della profondità di ricerca
    forniti dall'utente. Questo limite è PER RICERCA, il che significa che potrebbe esserlo
    superato se si utilizza la funzione geoblast o parola chiave.

    I cicli potrebbero interrompersi anticipatamente se non vengono trovate più corrispondenze o se viene eseguita una singola ricerca
    supera il limite di 1000 utilizzi non commerciali di LinkedIn.

    """

    # Cercheremo 50 nomi su ciascun ciclo. Quindi, impostiamo un importo massimo di
    # esegue un loop sulla quantità di personale / 50 +1 in più per catturare i resti.
    loops = int((staff_count / 50) + 1)

    print(f"[*] L'azienda ha {staff_count} profili da controllare. Alcuni potrebbero essere anonimi.")

    # Le righe seguenti tentano di rilevare set di risultati di grandi dimensioni e confrontarli
    # con gli argomenti della riga di comando passati. L'obiettivo è avvisare quando
    # potrebbe non ottenere tutti i risultati e suggerire modi per ottenerne di più.
    if staff_count > 1000 and not args.geoblast and not args.keywords:
        print("[!] Nota: LinkedIn ci limita a un massimo di 1000"
              "risultati!\n"
              " Prova il parametro --geoblast o --keywords da bypassare")
    elif staff_count < 1000 and args.geoblast:
        print("[!] Geoblast non è necessario, come ha fatto questa azienda"
              "Meno di 1.000 dipendenti. Disabilitante.")
        args.geoblast = False
    elif staff_count > 1000 and args.geoblast:
        print("[*] Elevato numero di dipendenti, geoblast è abilitato. Rockeggiamo.")
    elif staff_count > 1000 and args.keywords:
        print("[*] Elevato numero di dipendenti, utilizzando parole chiave. Spero che tu abbia scelto"
              "alcuni buoni.")

    # Se l'utente ha limitato di proposito la profondità della ricerca, probabilmente lo sa
    # cosa stanno facendo, ma li avvertiamo per ogni evenienza.
    if args.depth and args.depth < loops:
        print("[!] Hai definito una profondità di ricerca personalizzata bassa, quindi noi"
              "potrebbe non ottenerli tutti.\n\n")
    else:
        print(f"[*] Impostando ogni iterazione a un massimo di {loops} cicli di"
              " 50 risultati ciascuno.\n\n")
        args.depth = loops

    return args.depth, args.geoblast


def get_results(session, company_id, page, region, keyword):
    """
    Raschia i dati grezzi per l'elaborazione.

    L'URL seguente è ciò che il sito HTTP mobile di LinkedIn esegue manualmente
    scorrendo i risultati della ricerca.

    Per impostazione predefinita, il sito mobile utilizza un "conteggio" pari a 10, ma i test lo dimostrano
    50 è consentito. Questo comportamento apparirà al server web come qualcuno
    scorrendo velocemente tutti i risultati disponibili.
    """

    # Costruisci l'URL di ricerca di base.
    url = ('https://www.linkedin.com/voyager/api/graphql?variables=('
           f'start:{page * 50},'
           f'query:('
           f'{f"keywords:{keyword}," if keyword else ""}'
           'flagshipSearchIntent:SEARCH_SRP,'
           f'queryParameters:List((key:currentCompany,value:List({company_id})),'
           f'{f"(key:geoUrn,value:List({region}))," if region else ""}'
           '(key:resultType,value:List(PEOPLE))'
           '),'
           'includeFiltersInResponse:false'
           '),count:50)'
           '&queryId=voyagerSearchDashClusters.66adc6056cf4138949ca5dcb31bb1749')

    # Eseguire la ricerca per questa iterazione.
    result = session.get(url)
    return result


def find_employees(result):
    """
    Prende la risposta testuale di una query HTTP, la converte in JSON ed estrae i dettagli dei dipendenti.

    Restituisce un elenco di elementi del dizionario o False se non ne viene trovato nessuno.
    """
    found_employees = []

    try:
        result_json = json.loads(result)
    except json.decoder.JSONDecodeError:
        print("\n[!] Ops! Impossibile decodificare JSON durante lo scraping di questo ciclo! :(")
        print("Sto per rinunciare a estrarre i nomi ora, ma questo non è normale. Dovresti "
              "risolvere il problema o aprire un ticket per segnalare l'errore..")
        print("Ecco i primi 200 caratteri della risposta HTTP, che potrebbero essere utili per il debug::\n\n")
        print(result[:200])
        return False

    # Analizza i dati, facendo attenzione a evitare errori chiave
    data = result_json.get('data', {})
    search_clusters = data.get('searchDashClustersByAll', {})
    elements = paging = search_clusters.get('elements', [])
    paging = search_clusters.get('paging', {})
    total = paging.get('total', 0)

    # Se alla fine ci ritroviamo con dict vuoti o zero risultati rimasti, lanciamoci fuori dai guai
    if total == 0:
        return False

    # L'elenco "elementi" è il mini-profilo che vedi scorrendo a
    # dipendenti dell'azienda. Non contiene tutte le informazioni sulla persona, come le loro
    # intera storia lavorativa. Ha solo alcune nozioni di base.
    found_employees = []
    for element in elements:
        # Per qualche ragione è annidato
        for item_body in element.get('items', []):
            # Le informazioni che vogliamo sono tutte sotto "entityResult"
            entity = item_body['item']['entityResult']

            # Ci sono alcune voci inutili che dobbiamo saltare
            if not entity:
                continue

            # Non ci sono più campi nome/cognome, quindi prendiamo il nome completo
            full_name = entity['title']['text'].strip()

            # Il nome può includere extra come "Dr" all'inizio, quindi eseguiamo alcune operazioni di base
            if full_name[:3] == 'Dr ':
                full_name = full_name[4:]

            occupation = entity['primarySubtitle']['text']

            found_employees.append({'full_name': full_name, 'occupation': occupation})

    return found_employees


def do_loops(session, company_id, outer_loops, args):
    """
    Esegue il loop nel punto in cui si verificano le richieste HTTP effettive per lo scraping dei nomi

    Questo è suddiviso in una funzione individuale sia per ridurre la complessità ma anche per
    consentire che si verifichi un Ctrl-C e continuare a scrivere i dati che abbiamo raccolto finora.

    Il sito mobile utilizzato restituisce il JSON corretto, che viene analizzato in questa funzione.

    Ha il concetto di anelli interni ed esterni. Gli outerloop entrano in gioco quando
    utilizzando --keywords o --geoblast, entrambi che tentano di aggirare i 1.000
    limite di ricerca record.

    Questa funzione interromperà la ricerca se un ciclo restituisce 0 nuovi nomi.
    """
    # Creare l'URL corretto è un po' complicato, quindi al momento non è necessario
    # parametri sono ancora inclusi ma impostati su vuoti. Vedrai questo
    # di seguito con geoblast e parole chiave.
    employee_list = []

    # Vogliamo poter interrompere qui con Ctrl-C e continuare a scrivere i nomi che abbiamo
    try:
        for current_loop in outer_loops:
            if args.geoblast:
                region_name, region_id = list(GEO_REGIONS.items())[current_loop]
                current_region = region_id
                current_keyword = ''
                print(f"\n[*] Looping through region {region_name}")
            elif args.keywords:
                current_keyword = args.keywords[current_loop]
                current_region = ''
                print(f"\n[*] Looping through keyword {current_keyword}")
            else:
                current_region = ''
                current_keyword = ''

            # Questo è il ciclo interno. Cercherà i risultati 50 alla volta.
            for page in range(0, args.depth):
                new_names = 0

                sys.stdout.flush()
                sys.stdout.write(f"[*] Estrazione dei risultati in un ciclo {str(page+1)}...    ")
                result = get_results(session, company_id, page, current_region, current_keyword)

                if result.status_code != 200:
                    print(f"\n[!] Yikes, got an HTTP {result.status_code}. Questo non è normale, come luca ena")
                    print("Uscendo dai cicli, ma dovresti risolvere i problemi..")
                    break

                # Il limite di ricerca commerciale potrebbe essere attivato
                if "UPSELL_LIMIT" in result.text:
                    sys.stdout.write('\n')
                    print("[!] Hai raggiunto il limite di ricerca commerciale! "
                          "Riprova il primo giorno del mese. Spiacente. :(")
                    break

                found_employees = find_employees(result.text)

                if not found_employees:
                    sys.stdout.write('\n')
                    print("[*] Abbiamo raggiunto la fine della strada! Continuiamo...")
                    break

                new_names += len(found_employees)
                employee_list.extend(found_employees)

                sys.stdout.write(f"    [*] Aggiunti {str(new_names)} nuovi nomi. "
                                 f"Totale in esecuzione: {str(len(employee_list))}"
                                 "              \r")

                # Se l'utente ha definito uno sleep between loops, ne prendiamo un po'
                # fai un pisolino qui.
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\n\n[!] Caught Ctrl-C. Breaking loops and writing files")

    return employee_list


def write_lines(employees, name_func, domain, outfile):
    """
    Funzione di supporto per modificare i nomi e scrivere in un file di output

    Deve essere chiamato con una variabile stringa in name_func che corrisponde al metodo della classe
    nome nella classe NameMutator.
    """
    for employee in employees:
        mutator = NameMutator(employee["full_name"])
        if mutator.name:
            for name in getattr(mutator, name_func)():
                outfile.write(name + domain + '\n')

def write_files(company, domain, employees, out_dir):
    """
    Scrive i dati in vari file di output formattati.

    Una volta completata la raschiatura e l'elaborazione, questa funzione formatta il file raw
    nomi in formati di nome utente comuni e li scrive in una directory chiamata
    li2u-output se non diversamente specificato.

    Vedi i commenti in linea per le decisioni prese sulla gestione di casi speciali.
    """

    # Cerca e crea una directory di output per archiviare i file.
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # Scrivere tutti i nomi grezzi e mutati nei file
    with open(f'{out_dir}/{company}-rawnames.txt', 'w', encoding='utf-8') as outfile:
        for employee in employees:
            if employee['full_name'] != 'LinkedIn Member':
                outfile.write(employee['full_name'] + '\n')

    with open(f'{out_dir}/{company}-metadata.txt', 'w', encoding='utf-8') as outfile:
        outfile.write('full_name,occupation\n')
        for employee in employees:
            mutator = NameMutator(employee["full_name"])
            if mutator.name and 'linkedin member' not in mutator.name['first'].lower() and 'l.member' not in mutator.name['first'].lower():
                for name in mutator.f_dot_last():
                    if 'linkedin member' not in name.lower() and 'l.member' not in name.lower():
                        outfile.write(employee['full_name'] + ',' + employee["occupation"] + '\n')

    with open(f'{out_dir}/{company}-f.last.txt', 'w', encoding='utf-8') as outfile:
        for employee in employees:
            mutator = NameMutator(employee["full_name"])
            if mutator.name and 'linkedin member' not in mutator.name['first'].lower() and 'l.member' not in mutator.name['first'].lower():
                for name in mutator.f_dot_last():
                    if 'linkedin member' not in name.lower() and 'l.member' not in name.lower():
                        outfile.write(name + domain + '\n')

    #with open(f'{out_dir}/{company}-firstl.txt', 'w', encoding='utf-8') as outfile:
    #   for employee in employees:
    #       mutator = NameMutator(employee["full_name"])
    #       if mutator.name and 'linkedin member' not in mutator.name['first'].lower() and 'l.member' not in mutator.name['first'].lower():
    #           for name in mutator.first_l():
    #                if 'linkedin member' not in name.lower() and 'linkedin.m' not in name.lower():                     
    #                   outfile.write(name + domain + '\n')

    #with open(f'{out_dir}/{company}-first.last.txt', 'w', encoding='utf-8') as outfile:
    #    for employee in employees:
    #        mutator = NameMutator(employee["full_name"])
    #        if mutator.name and 'linkedin member' not in mutator.name['first'].lower() and 'l.member' not in mutator.name['first'].lower():
    #            for name in mutator.first_dot_last():
    #                if 'linkedin member' not in name.lower() and 'linkedin.member' not in name.lower():
    #                    outfile.write(name + domain + '\n')

    #with open(f'{out_dir}/{company}-first.txt', 'w', encoding='utf-8') as outfile:
    #    for employee in employees:
    #        mutator = NameMutator(employee["full_name"])
    #        if mutator.name and 'linkedin member' not in mutator.name['first'].lower() and 'l.member' not in mutator.name['first'].lower():
    #            for name in mutator.first():
    #                if 'linkedin member' not in name.lower() and 'linkedin' not in name.lower():
    #                    outfile.write(name + domain + '\n')

    #with open(f'{out_dir}/{company}-lastf.txt', 'w', encoding='utf-8') as outfile:
    #    for employee in employees:
    #        mutator = NameMutator(employee["full_name"])
    #        if mutator.name and 'linkedin member' not in mutator.name['first'].lower() and 'l.member' not in mutator.name['first'].lower():
    #            for name in mutator.last_f():
    #                    if 'linkedin member' not in name.lower() and 'member.l' not in name.lower():
    #                       outfile.write(name + domain + '\n')

def main():
    """Main Function"""
    print(BANNER + "\n\n\n")
    args = parse_arguments()

    # Crea un'istanza di una sessione accedendo a LinkedIn.
    session = login()

    # Se non riusciamo ad ottenere una sessione valida, usciamo adesso. Gli errori specifici sono
    # stampato sulla console all'interno della funzione login().
    if not session:
        sys.exit()

    # Opzioni speciali di seguito quando si utilizza un server proxy. Utile per il debug
    # l'applicazione in Burp Suite.
    if args.proxy:
        print("[!] Utilizzando un proxy, ignorando gli errori SSL. Non farti pwnare.")
        session.verify = False
        urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)
        session.proxies.update(args.proxy_dict)

    # Ottieni informazioni di base sull'azienda
    print("[*] Sto cercando di ottenere informazioni sull'azienda...")
    company_id, staff_count = get_company_info(args.company, session)

    # Definisce i cicli interni ed esterni
    print("[*] Calcolando i cicli interni ed esterni...")
    args.depth, args.geoblast = set_inner_loops(staff_count, args)
    outer_loops = set_outer_loops(args)

    # Esegui la ricerca vera e propria
    print("[*] Avvio della ricerca... Premi Ctrl-C per interrompere e scrivere i file in anticipo..\n")
    employees = do_loops(session, company_id, outer_loops, args)

    # Scrivere i dati in alcuni file.
    write_files(args.company, args.domain, employees, args.output)

    # È ora di iniziare l'hacking
    print(f"\n\n[*] Tutto fatto! Dai un'occhiata ai tuoi nuovi file generati in {args.output}")


if __name__ == "__main__":
    main()
