import azure.functions as func
import requests
import json
import logging
import os
from openai import AzureOpenAI
import re
import logging
client = AzureOpenAI(
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version="2024-05-01-preview"
        )
class ExamenFetcher:
    def __init__(self):
        self.url = "https://sandbox.xplore.fr:20443/XaPriseRvGateway/Application/api/External/GetListeExamensFromTypeExamen"
        self.headers = {'Content-Type': 'application/json'}
        self.ids_base = {'CT', 'US', 'MR', 'MG', 'RX'}
        self.llm_model = "gpt-35-turbo"
        self.replacements = {
                r'acromioclaviculaire': "ACROMIOCLAVICULAIRE (RADIOGRAPHIE DE L'ARTICULATION ACROMIO-CLAVICULAIRE)",
                r'pangonogramme': "PANGONOGRAMME (RADIOGRAPHIE DES DENTS)",
                r'asp': "ASP (RADIOGRAPHIE DE L'ABDOMEN SANS PRÉPARATION)",
                r'urocanner': "UROSCANNER (SCANNER DES REINS)",
                r'arm': "ARM (IRM DES VAISSEAUX SANGUINS)",
                r'bili[- ]?irm': "BILI IRM (IRM DES VOIES BILIAIRES)",
                r'entero[- ]?irm': "ENTERO IRM (IRM DE L'INTESTIN)",
                r'entéro[- ]?irm': "ENTERO IRM (IRM DE L'INTESTIN)",
                r'angio[- ]?irm': "ANGIO IRM (IRM ANGIOGRAPHIQUE DES VAISEAUX SANGUINS)",
                r'uro[- ]?scanner': "UROSCANNER (SCANNER DES VOIES URINAIRES)",
                r'dacryoscanner': "DACRYOSCANNER (SCANNER DES VOIES LACRYMALES)",
                r'coroscanner': "COROSCANNER (SCANNER DES ARTÈRES DU CŒUR)",
                r'entéroscanner': "ENTEROSCANNER (SCANNER DE L'INTESTIN)",
                r'coloscanner': "COLOSCANNER (SCANNER DU COLON)",
                r'arthro[- ]?scanner': "ARTHRO-SCANNER (SCANNER DES ARTICULATIONS)",
                r'arthro[- ]?irm': "ARTHRO-IRM (IRM DES ARTICULATIONS)",
                r'ostéodensitométrie': "OSTÉODENSITOMÉTRIE (RADIOGRAPHIE DES OS)",
                r'cystographie': "CYSTOGRAPHIE (RADIOGRAPHIE DE LA VESSIE)",
                r'discographie': "DISCOGRAPHIE (RADIOGRAPHIE DU DISQUE INTERVERTÉBRAL)",
                r'togd': "TOGD (RADIOGRAPHIE DE L'ŒSOPHAGE ET DE L'ESTOMAC)",
                r'urographie': "UROGRAPHIE (RADIOGRAPHIE DES VOIES URINAIRES)",
                r'hystérographie': "HYSTÉROGRAPHIE (RADIOGRAPHIE DE LA CAVITÉ UTÉRINE)",
                r'hystérosalpingographie': "HYSTÉROSALPINGOGRAPHIE (RADIOGRAPHIE DE LA CAVITÉ UTÉRINE)",
                r'cone[- ]?beam': "CONE BEAM (RADIOGRAPHIE DES DENTS)",
                r'tomographie': "TOMOGRAPHIE (RADIOGRAPHIE DES DENTS)",
                r'doppler': "DOPPLER (ÉCHOGRAPHIE DES VAISSEAUX)",
                r'echodoppler': "ECHODOPPLER (ÉCHOGRAPHIE DOPPLER)",
                r'echocardiographie': "ECHOCARDIOGRAPHIE (ÉCHOGRAPHIE DU CŒUR)",
                r'cerebro[- ]?scanner': "CEREBROSCANNER (SCANNER DU CERVEAU)",
                r'echographie[- ]?endor[ée]?ctale': "ÉCHOGRAPHIE ENDORÉCTALE (ÉCHOGRAPHIE DU RECTUM)",
                r'echographie[- ]?endovaginale': "ÉCHOGRAPHIE ENDOVAGINALE (ÉCHOGRAPHIE DU VAGIN ET DE L'UTÉRUS)"}

        self.keywords = {
            "RADIO": ["radio", "radiographie"],
            "SCANNER": ["scanner", "tdm", "tomodensitométrie", "scan"],
            "IRM": ["irm", "imagerie par résonance magnétique",'rmn'],
            "ECHOGRAPHIE": ["echo", "écho", "échographie", "echographie", "échotomographie"],
            "MAMMOGRAPHIE": ["mammographie", "mammogramme", "mammo", "mamographie", "sein", "mammaire"],
            'IMAGERIE':['imagerie']
        }

    def get_type_examen(self , texte):
        if not texte or not texte.strip():
            logging.warning("Texte vide ou invalide fourni à get_type_examen")
            return "AUTRE"
        titre_normalise = texte.lower()
        for pattern, replacement in self.replacements.items():
            titre_normalise = re.sub(pattern, replacement, titre_normalise, flags=re.IGNORECASE)
        for category, words in self.keywords.items():
            if any(word in titre_normalise for word in words):
                logging.info(f"Type d'examen identifié: {category}")
                return category
        logging.info("Aucun type d'examen trouvé, retour par défaut: AUTRE")
        return "AUTRE"

    def fetch_examens(self, ids=None):
        if ids is None:
            ids = self.ids_base
        else:
            ids = {id.upper() for id in ids if id.upper() in self.ids_base}
        
        data = {}
        with requests.Session() as session:
            session.headers.update(self.headers)
            for id in ids:
                try:
                    payload = json.dumps({"id": id})
                    response = session.post(self.url, data=payload, timeout=10)
                    
                    if response.status_code == 200:
                        actes = response.json().get('data', [])
                        data = {acte['code']: acte['libelle'] for acte in actes}
                        logging.info(f"Données récupérées pour ID {id}: {data}")
                    else:
                        logging.info(f"Erreur {response.status_code} pour l'ID {id}")
                except requests.RequestException as e:
                    logging.info(f"Erreur lors de la requête pour {id}: {e}")
        return data

    def get_class(self, text, data):
        custom_prompt_template = (
            f"Voici la liste des examens médicaux proposés par notre centre d'imagerie médicale : {', '.join(data.values())}. \n"
            f"Veuillez analyser la phrase suivante exprimée par un patient et identifier l'examen le plus adapté à son besoin. "
            f"Répondez uniquement par le nom de l'examen correspondant.Si aucun ne convient répondre par 'None' "
        )
        try:
            completion = client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": custom_prompt_template},
                    {"role": "user", "content": text}
                ],
            )
            logging.info(f"Réponse du modèle : {completion.choices[0].message.content}")
            return completion.choices[0].message.content
        except Exception as e:
            logging.error(f"Error answering query: {e}")
            return "Une erreur est survenue lors de la réponse."

    def lyae_talk_exam(self, texte):
      exam_types = {
          "RADIO": "RX",
          "SCANNER": "CT",
          "IRM": "MR",
          "ECHOGRAPHIE": "US",
          "MAMMOGRAPHIE": "MG",
          'AUTRE' :None
      }
      type_exam = self.get_type_examen(texte)
      id = exam_types.get(type_exam)
      if not id:
          logging.warning("Aucun ID correspondant trouvé")
          return None, None , None , None
      
      actes = self.fetch_examens([id])
      code_exam = self.get_class(texte, actes)
      code_exam_id = next((k for k, v in actes.items() if v == code_exam), None)
      logging.info(f"Résultat final: Type {type_exam}, ID {id}, Code Examen {code_exam}, Exam Code {code_exam_id}")
      return type_exam,id, code_exam , code_exam_id

fetcher = ExamenFetcher()

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
        query = req_body.get('text')

        if not query:
            return func.HttpResponse(
                json.dumps({"error": "No query provided in request body"}),
                mimetype="application/json",
                status_code=400
            )

        type_examen ,type_examen_id, code_examen , code_examen_id = fetcher.lyae_talk_exam(query)
        return func.HttpResponse(
            json.dumps({"type_examen": type_examen , "type_examen_id":type_examen_id , "code_examen":code_examen , "code_examen_id": code_examen_id}),
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
