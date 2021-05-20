from flask import Flask, request, jsonify
from apiclient.discovery import build
from apiclient import errors
import pickle
from datetime import timedelta, datetime, timezone
from dateutil import tz
import os
import json
from dotenv import load_dotenv,dotenv_values
#load_dotenv()
 # adjust as appropriate
load_dotenv()
#print(os.path.join(project_folder, '.env'))
app = Flask(__name__)


@app.route("/book_appt", methods=['GET','POST'])
def book_appt():
    """
        Incoming autopilot task: book_appointments
        Routes to: complete_appt and notify_no_availability
    """
    print(dotenv_values(".env"))
    memory = json.loads(request.form.get('Memory'))
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    #print(calendar_id)
    if 'appt_id' in memory and memory['appt_id'] != "":
        # User left an unfinished booking in the conversation due to an error
        cancel_event(calendar_id, memory['appt_id'])

    # Delete draft events that were left unfinished and have more than 5
    # minutes of being created
    delete_draft_events(calendar_id)

    answers = memory[
        'twilio']['collected_data']['book_appt']['answers']

    appt_time = answers['appt_time']['answer']
    appt_date = answers['appt_date']['answer']
    start_time_str = appt_date + ' ' + appt_time
    start_time_obj = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M')
    tzinfo = tz.gettz(os.environ.get("LOCAL_TIMEZONE"))
    start_time_obj = start_time_obj.replace(tzinfo=tzinfo)
    print(start_time_obj)
    appt_type = answers['appt_type']['answer'] #subject of the meeting
    appt_meet_time = int(answers['appt_meet_time']['answer'])
    appt_meet_type = int(answers['appt_meet_type']['answer'])
    Recurrence = ''
    
    if appt_meet_type == 1:
       response = {
            "actions": [{
                    "redirect": "task://recurring_meeting"
                },
                {
                    "remember": {
                        "appt_type" : appt_type,
                        "start_time_str": start_time_str,
                        "appt_meet_time" : appt_meet_time,
                        "appt_meet_type" : appt_meet_type
                    }
                }
            ]
        }
    else:
        available_event_id = check_availability(
        calendar_id, start_time_obj, appt_type,appt_meet_time,appt_meet_type,Recurrence)
        if available_event_id:
            response = {
            "actions": [{
                    "redirect": "task://complete_booking"
                },
                {
                    "remember": {
                        "appt_id": available_event_id
                    }
                }
            ]
            }
        else:
           response = {
            "actions": [{
                "redirect": "task://notify_no_availability"
            }]
            }
    



    

    return jsonify(response)

@app.route("/recurring_meeting", methods=['POST'])   
def recurring_meeting():
    type_d = ""
    #print(hello)
    memory = json.loads(request.form.get('Memory'))
    start_time_str = memory['start_time_str']
    start_time_obj = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M')
    tzinfo = tz.gettz(os.environ.get("LOCAL_TIMEZONE"))
    start_time_obj = start_time_obj.replace(tzinfo=tzinfo)
    appt_meet_type = memory['appt_meet_type']
    app_type = memory['appt_type']
    appt_meet_time = memory['appt_meet_time']
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    answers = memory[
        'twilio']['collected_data']['recurring_appt']['answers'] 
    repeat_type = int(answers['appt_rep_type']['answer'])
    count = answers['appt_count']['answer']
    if repeat_type == 1:
       type_d = "DAILY"
    elif repeat_type == 2:
       type_d =  "WEEKLY"
    elif repeat_type == 3:
        type_d =  "MONTHLY"
    elif repeat_type == 4:
        type_d =  "YEARLY"
    Recurrence = "RRULE:FREQ="+type_d+";COUNT="+count
    #Recurrence = str(Recurrence)
    #Recurrence = 'RRULE:FREQ=MONTHLY;COUNT=5'
    print(Recurrence)
    available_event_id = check_availability(
        calendar_id, start_time_obj, app_type,appt_meet_time,appt_meet_type,Recurrence)
    if available_event_id:
            response = {
             "actions": [{
                    "redirect": "task://complete_booking"
                },
                {
                    "remember": {
                        "appt_id": available_event_id
                    }
                }
            ]
            }
    else:
           response = {
            "actions": [{
                "redirect": "task://notify_no_availability"
            }]
            }
    return jsonify(response)
    
    
@app.route("/complete_booking", methods=['POST'])
def complete_booking():
    """
        Incoming autopilot task: complete_booking
        Routes to: confirm_booking or book_appointments
    """
    memory = json.loads(request.form.get('Memory'))
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    answers = memory[
        'twilio']['collected_data']['complete_appt']['answers']

    appt_title = answers['appt_title']['answer']
    appt_email = answers['appt_email']['answer']
    event_id = memory['appt_id']

    event = update_event(
        event_id=event_id,
        calendar_id=calendar_id,
        title=appt_title,
        start_time='',
        service_type='',
        email=appt_email)

    if event['status'] == 'cancelled':
        # Cancelled due to time limit exceeded during reservation and another
        # user started a booking process
        response = {
            "actions": [{
                "say": "I'm sorry. The time limit to confirm the reservation "
                "has been exceeded. Please try again."
            }, {
                "remember": {
                    "appt_id": ""
                }
            }, {
                "redirect": "task://book_appointments"
            }]
        }
    else:
        response = {
            "actions": [{
                "say": "Thanks! I've booked your appointment, you can check "
                "your email for confirmation now. See you soon :)"
            }]
        }

    return jsonify(response)
    
    
@app.route("/cancel_appt", methods=['POST'])
def cancel_appt():
    """
        Incoming autopilot task: cancel_appointments
        Routes to: confirm_cancel or error response message
    """
    memory = json.loads(request.form.get('Memory'))
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    answers = memory[
        'twilio']['collected_data']['cancel_appt']['answers']
    appt_email = answers['appt_email']['answer']
    #next_event = get_next_event_from_user(calendar_id, appt_email)
    time_min = datetime.now(timezone.utc).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()

    service = create_service()

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents="True",
        orderBy="startTime"
    ).execute()
    print(events_result)
    #event_result = []
    
    for item in events_result['items']:
        event_start = datetime.strptime(
            item['start']['dateTime'],
            "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
        # There should always be an attendee and it will always be only one
        if 'attendees' in item \
                and item['attendees'][0].get('email') == appt_email \
                and event_start > datetime.now():
            next_event= item
            if  next_event is None:
                    response = {
                        "actions": [
                          {
                         "say":
                        "I'm sorry. I couldn't find any appointment with the "
                         "email address provided."
                        }
                        ]
                   }
            else:
               event_id = next_event['id']
               cancel_result = cancel_event(calendar_id, event_id)

    if cancel_result:
        response = {
            "actions": [{
            "say": "Okay! I've cancelled your appointment. Thank you for contacting us."
              }]
             }
    else:
        response = {
          "actions": [{
          "say": "There was an error. Please try again later."
             }]
             }

    return jsonify(response)

def get_details_of_duration(service_time):
    """
        Returns a duration value in minutes 
        Service types:
            1. 30 mins
            2. 45 mins
            3. 60 mins
    """
    if service_time == 1:
        return  30
    elif service_time == 2:
        return  45
    elif service_time == 3:
        return  60
        


def create_service():
    """
        Creates and returns a Google Calendar service from a pickle file
        previously generated.
    """

    with open("token.pickle", "rb") as token:
        credentials = pickle.load(token)

    service = build("calendar", "v3", credentials=credentials)

    return service


def check_availability(calendar_id, start_time, service_type,meet_time,meet_type,Recurrence):
    """
        Checks if there is an event already created at the specific date and
        time provided and creates a temporary one to reserve the spot.
        Parameters:
            - calendar_id
            - start_time
            - service_type
        Returns: id of the created event or None if the spot is not available.
    """
    duration = get_details_of_duration(meet_time)
    type_description = service_type
    time_min = start_time.astimezone(tz.tzutc()).isoformat()
    time_max = (start_time + timedelta(minutes=duration)) \
        .astimezone(tz.tzutc()).isoformat()
    #Recurrence =  'RRULE:FREQ=WEEKLY;COUNT=10'
    service = create_service()
    
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        
    ).execute()
    print(events_result)
    event_id = None

    if events_result['items'] == []:
       #print(events_result['items'][0])
       print(events_result['items'])
        # Creates a draft event to reserve the spot after checking availability
       if meet_type == 1:
             #memory = json.loads(request.form.get('Memory'))
             #Recurrence = memory['']           
           event = create_recurring_event( calendar_id, start_time, duration, type_description,Recurrence)
            
       else: 
           event = create_event( calendar_id, start_time, duration, type_description)
       event_id = event['id']

    return event_id


def delete_draft_events(calendar_id):
    """
        Deletes events with no email assigned in a period of 60 days and has
        been more than 5 minutes of being created. This means that:
            - A user started a booking process, the spot was reserved but
            ended the conversation halfway through (fallback action or simply
            left) or
            - A user started a booking process but took more than 5 minutes to
            fill all the information to get a confirmation and another user
            started another process
        Parameter:
            - calendar_id
    """
    time_min = datetime.now(timezone.utc).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()

    service = create_service()

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        
        singleEvents="True",
        orderBy="startTime"
    ).execute()

    for item in events_result['items']:
        start_time = datetime.strptime(
            item['created'], "%Y-%m-%dT%H:%M:%S.%f%z")
        time_diff_delta = datetime.now(timezone.utc) - start_time
        time_diff_mins = time_diff_delta.total_seconds() / 60

        if 'attendees' not in item and time_diff_mins > 5:
            cancel_event(calendar_id, item['id'], service)
def create_recurring_event(calendar_id, start_time, duration, type_description,Recurrence):
    """
        Creates an event on the calendar.
        Parameters:
            - calendar_id
            - start_time in datetime.datetime format
            - duration of the appointment that will be used to calculate the
            end time of the event
            - type_description
        Returns: Event structure as confirmation
    """
    location = "Popp Martin Student Union,9201 University City Blvd, Charlotte, NC 28223"
    end_time = start_time + timedelta(minutes=duration)

    event = {
        'location': location,
        'description': type_description,
        'start': {
            'dateTime': start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            'timeZone': os.environ.get("LOCAL_TIMEZONE")
        },
        'end': {
            'dateTime': end_time.strftime("%Y-%m-%dT%H:%M:%S"),
            'timeZone': os.environ.get("LOCAL_TIMEZONE")
        },
        'recurrence': [
        Recurrence
        ]
        
    }
    print(event)
    service = create_service()

    create_recurring_event = service.events().insert(
        calendarId=calendar_id,
        body=event,
        sendNotifications=True
    ).execute()

    return create_recurring_event

def create_event(calendar_id, start_time, duration, type_description):
    """
        Creates an event on the calendar.
        Parameters:
            - calendar_id
            - start_time in datetime.datetime format
            - duration of the appointment that will be used to calculate the
            end time of the event
            - type_description
        Returns: Event structure as confirmation
    """
    location = "Popp Martin Student Union, Student Union, University City Boulevard, Charlotte, NC"
    end_time = start_time + timedelta(minutes=duration)

    event = {
        'location': location,
        'description': type_description,
        'start': {
            'dateTime': start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            'timeZone': os.environ.get("LOCAL_TIMEZONE")
        },
        'end': {
            'dateTime': end_time.strftime("%Y-%m-%dT%H:%M:%S"),
            'timeZone': os.environ.get("LOCAL_TIMEZONE")
        },
        
    }

    service = create_service()

    create_event = service.events().insert(
        calendarId=calendar_id,
        body=event,
        sendNotifications=True
    ).execute()

    return create_event


def cancel_event(calendar_id, event_id, service=None):
    """
        Deletes an event from the calendar. This could be a deletion of a draft
        event, or an appointment cancellation.
        Parameters:
            - event_id
            - calendar_id
            - service. Default: None
        Returns: boolean. True if service was cancelled correctly or False if
        there was an error.
    """
    if not service:
        service = create_service()

    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except errors.HttpError as e:
        print(e)
        return False
    else:
        return True
def update_event(
        event_id, calendar_id, title, start_time, service_type, email):
    """
        Updates event.
        Parameters:
            - calendar_id
            - event_id
            - start_time in a datetime.datetime format
            - end_time in a datetime.datetime format
        Returns: Event structure as confirmation
    """
    summary = "{}'s appointment".format(title)

    body = {
        'summary': summary,
        'attendees': [
            {'email': email},
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 30}
            ],
        }
    }

    service = create_service()

    update_event = service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body=body,
        sendUpdates='all'
    ).execute()

    return update_event
'''
def get_next_event_from_user(calendar_id, appt_email):
    """
        Returns a list of all the events on a specific calendar from the
        next 30 days.
        Parameters:
            - calendarId
            - email
        Returns: Dict structure with the nearest event in case one is found.
        None if no event was found
    """

    time_min = datetime.now(timezone.utc).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()

    service = create_service()

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents="True",
        orderBy="startTime"
    ).execute()
    print(events_result)
    event_result = []
    
    for item in events_result['items']:
        event_start = datetime.strptime(
            item['start']['dateTime'],
            "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
        # There should always be an attendee and it will always be only one
        if 'attendees' in item \
                and item['attendees'][0].get('email') == appt_email \
                and event_start > datetime.now():
            event_result = item
            
           # break  # Because we will only return the first occurence
    print(event_result)
    return event_result
'''
if __name__ == "__main__":
    app.run(debug=True)