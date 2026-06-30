# from app import status
from flask import Flask
from flask import json, Flask
from db import initialize_db
from bson import json_util
# from models import User,Organization,Countries,States,Cities,User1,Fields,Numbering,Module_name,User_module_name,Timezones,Contact,Contact1,Activity,Account,Follow_up,Note,Product,Deal,Email,Document,Quote,PdfSettings,Proforma,Role,Invoice,Email_template,Rename,SalesProcess,SalesSubProcess,DealsCheckList,DealsSubCheckList,SalesProcessTemplate,DealsStageMapping,AdminEmailTemplate,Reporting_To,SupportTicket,Enquiry,Partner,Accounttmp,Contacttmp,Producttemp,User_audit,AdminUser
from models import AdminUser,  Organization,User, User_audit,Contact,User_audit,Partner_user,Partner,Timezones,Admin_contacts,Currencies,Reporting_To,Plan_wise_modules,Admin_fields,Admin_lead,Admin_notes,Admin_email,Admin_document,Admin_activity,Admin_quote,PdfSettings,Countries
# ===> ( OrgAddon,AddOn ) to be add in above for addon feature
from bson import ObjectId
import datetime
from pytz import timezone   
from mongoengine.errors import NotUniqueError
from collections import defaultdict
import app_config
from mongodb import TokenRefresh

from datatable import LastDataId
from common_config import Uid
from mongodb import MongoAPI
from datetime import date, timedelta  
# from flask_session import Session

app = Flask(__name__)

# SESSION_TYPE = 'user'
# Session(app)


DATE_FORMAT1 = '%d/%m/%Y'

DATE_FORMAT_mdy = '%m/%d/%Y'

DATE_FORMAT2 = '%H:%M %p'

DATE_FORMAT3 = '%Y-%m-%d %H:%M:%S'

DATE_FORMAT = '%Y-%m-%d %H:%M:%S.%f'

DATE_FORMAT4 = '%Y-%m-%d %H:%M:%S'

USER_DATE_FORMAT1 = '%m-%d-%y'

USER_DATE_FORMAT2 = '%d-%m-%Y'

USER_DATE_FORMAT3 = '%m-%d-%Y'

app.config.from_pyfile('config.cfg')
app.config['UPLOAD_PDF_IMAGE_FOLDER'] = app_config.UPLOAD_PDF_IMAGE_FOLDER

initialize_db(app)

# //////////////////////////////////   ADMIN PANNEL WORK START - NAVEEN   ////////////////////////////////////////////////////////
class AdminAPI:
    def partner_user_Check(email):
        try:
            s = Partner_user.objects.get(email=email)
            if s.email:
                output = 'Yes'
            else:
                output = 'No'
                
        except Partner_user.DoesNotExist:
            output = 'No'   

        return output
    
    def create_partner_recordID(email, name):
        try:
            lastDataId = LastDataId.getPartnerLastDataId('partner_record_id')
            lastDataId = int(lastDataId) + 1

            # Get the last record's partner_no, or start with 100 if no records exist
            last_partner = Partner.objects.order_by('-partner_no').first()
            last_partner_no = last_partner.partner_no if last_partner and last_partner.partner_no else 99  # Default to 99 if none exists
            new_partner_no = last_partner_no + 1
            
            oneyear = datetime.datetime.now() + datetime.timedelta(days=365)
            
            partner = Partner(partner_record_id=lastDataId, name=name, email=email, partner_no=new_partner_no)
            response = partner.save()
            
            record_id = lastDataId
            partner_id = partner.id
            
        except NotUniqueError as e:
            record_id = '0'
            partner_id = None
        
        return record_id, partner_id

    
    def createPartnerUser(email,password,name,partner_id):
        try:
            data1 = defaultdict(list)
            data1['email'] = email
            data1['password'] = password
            data1['name'] = name
            data1['partner_id'] = partner_id
            user = Partner_user(**data1)
            response = user.save()
            print (data1,"hghghghgghhghgghnvnvb")
            output1 = response
            return output1
        except NotUniqueError as e:
            return ''
    
    def Select_Partner_Login(email,password):
        try:
            s = Partner_user.objects.get(email=email,password=password)
            id1 = json.loads(json_util.dumps(s.partner_id))
            id12 = json.loads(json_util.dumps(s))
            id = str(s.id)
            output1 = {'name' : s.name,'email' : s.email,'create_date' : s.create_date,'id':id,'status':s.status}
            output = output1
        except Partner_user.DoesNotExist:
            output = 'User Does Not Exists'        
        return output
    
    def partner_email_check(email):
        try:
            s = Partner_user.objects.get(email=email)
            output = 'Yes'
        except Partner_user.DoesNotExist:
            output = 'No'   

        return output
    
    def partner_Login_gmail(email):
       
        try:
            # password = generate_password_hash(password)
            # print (password)
            s = Partner_user.objects.get(email=str(email))
            id1 = json.loads(json_util.dumps(s.partner_id))
            id12 = json.loads(json_util.dumps(s))
            id = str(s.id)
            output1 = {'partner_id' : str(s.partner_id),'name' : s.name,'email' : s.email,'create_date' : s.create_date,'id':id,'status':s.status}
            output = output1
            # print (output,'ooooooooooooo')
        except User.DoesNotExist:
            output = 'no such name'        
        return output
    
    def PartnerCheck(id):
        try:
            filter = {}
            filter['_id'] = ObjectId(id)
            filter['status'] = 'active'
            match = filter
            pipeline = [
                            # {'$lookup': app_config.role_lookup},
                            {'$match'  : match}
                        ]
           
            settings = defaultdict(list)
            role = Partner_user.objects.aggregate(*pipeline)

            settings6=[]
            
            item4 = role
            
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    elif item1=='_id':
                        settings['id'] = item[item1]
                    elif item1=='org_id':
                        settings['org_id'] = int(item[item1])
                    elif item1=='roleData':
                        assigned = item[item1]
                        for item2 in assigned:
                            for item3 in item2:
                                if item3=='_id':
                                    role_key = str('role')+str(item3)
                                else:
                                    role_key = str('role_')+str(item3)
                                # print (role_key)
                                settings[role_key] = item2[item3]
                    else:
                        data = {item1:item4}
                    if not settings['source_name']:
                        settings['source_name']=''
                    if not settings['roleData']:
                        settings['roleData']=''
                    if not settings['stateId']:
                        settings['stateId']=''
                    if not settings['countryId']:
                        settings['countryId']=''
                    if not settings['pincode']:
                        settings['pincode']=''
                    if not settings['company_name']:
                        settings['company_name']=''            
            settings2 = json.loads(json_util.dumps(settings))
            
            # print (json.loads(settings2))
            settings2 = Uid.fix_array4(settings2)
            # print(settings2)
            # session['user'] = settings2

            # print (session['user'])

            return settings2
        except User.DoesNotExist:
            output = 'No'   

        return output
    
    def partnercommontimeset(current_user,partner_id):
        try:
            timezone = []
            if current_user:
                user = AdminAPI.PartnerCheck(current_user)
                if 'time_zone' in user:
                    if user['time_zone']:
                        timezone=user['time_zone']
                    else :
                        timezone=AdminAPI.partnertimezone(partner_id)  
                offset=AdminAPI.offesettimezone(timezone)
            else:
                offset=5.5
   
            # s = Timezones.objects.filter(text=timezone).to_json()
            # output = json.loads(s)
            # output = Uid.fix_array(output)
            # # offset = 5.5
            # for contact2 in output:
            #     for contact3 in contact2:
            #         if contact3=='offset':
            #             offset = contact2[contact3]
            #         else:
            #             offset = 5.5
            # output = offset
        except User.DoesNotExist:
            output = 'no such time_zone'        
        return offset
    
    def partnertimezone(partner_id):
        try:
            s = Partner.objects.filter(id=partner_id).to_json()
            output = json.loads(s)
            output = Uid.fix_array(output)

            time_zone = ''
            for contact2 in output:
                for contact3 in contact2:
                    if contact3=='time_zone':
                        time_zone = contact2[contact3]
            output = time_zone
        except User.DoesNotExist:
            output = 'no such time_zone'        
        return output

    def offesettimezone(timezone):
        try:
            offset = 5.5
            s = Timezones.objects.filter(text=timezone).to_json()
            output = json.loads(s)
            output = Uid.fix_array(output)
            # offset = 5.5
            for contact2 in output:
                for contact3 in contact2:
                    if contact3=='offset':
                        offset = contact2[contact3]
                    else:
                        offset = 5.5
            output = offset
        except Partner.DoesNotExist:
            output = 'no such time_zone'        
        return output
    
    def getAdminEmailAll():
        try:
            # test = Admin_email.objects(org_id=94).delete()
            # test2 =Email.objects().update(status='1')
            filter = {}
            key = []
            val = []
            # filter['org_id'] = org_id
            # if id :
            filter['status'] = '0'
            filter['email_type'] = 'bulk'
            
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$lookup': app_config.adminownerLookup},
                            {'$match': match},
                            {'$limit'  : 10},
                            {'$project': app_config.admin_email_Project}
                       ]
            role = Admin_email.objects.aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    # if item1=='create_date':
                    #     create_date1 = item[item1]
                    #     create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                    #     create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                    #     settings['create_date'] = create_date
                    #     settings['create_time'] = create_time
                    # if item1=='date':
                    #     create_date1 = item[item1]
                    #     create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                    #     settings['date'] = create_date
                    # if item1=='attachment':
                    #     if len(item[item1]) > 0:
                    #         attachment1 = item[item1]
                    #         attachment = []
                    #         for item3 in attachment1:
                    #             # attachment2 = str(app_config.BASE_URL)+str(app_config.UPLOAD_OPEN_EMAIL_FOLDER)+str(item3)
                    #             attachment2 = str(app_config.UPLOAD_OPEN_EMAIL_FOLDER)+str(item3)
                    #             # attachment2 =''+str(app_config.UPLOAD_OPEN_EMAIL_FOLDER)+str(item3)
                    #             attachment.append(attachment2)
                    #         settings['attachment'] = attachment
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''



                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def AdminemailSent(id):
        try:
            # print(id)
            data5 = defaultdict(list)
            Admin_email.objects(id=id).update(status='1')
            output1 = id
            return output1
        except NotUniqueError as e:
            return '0' 
    

    def search_partner_list(partner_id, current_user, search_string):
        try:
            # match ={}
            # match['assigned_to'] = {'$in': [ObjectId(current_user)]}
            # print(match,'mmmmmmmmmmmmmm')
            

            pipeline = [
                # {'$match': match},
                {'$match':{
                    '$or': [
                    {'name': { "$regex": search_string, "$options" :'i'}}, 
                    {'phone': { "$regex": search_string, "$options" :'i'}}, 
                    {'email': { "$regex": search_string, "$options" :'i'}},
                    {'status': { "$regex": search_string, "$options" :'i'}},
                    {'create_date': { "$regex": search_string, "$options" :'i'}}, 
                    ],         
                }},
                #  {'$lookup': app_config.task_priority_lookup},
            ]

            tasks = Partner.objects.aggregate(*pipeline)
            # print(str(tasks),pipeline,'str')
            settings6 = []
            for item in tasks:
                # print(item,'iiiiiiiii')
                settings = defaultdict(list)
                for item1 in item:
                    # settings = defaultdict(list)
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(current_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)

                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    
                    if item1=='due_date':
                        due_date = item[item1] 

                        # print(target_date)
                        create_date = datetime.datetime.strptime(str(due_date), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        # create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        # create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['due_date'] = create_date

                    
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            # total_count = next(count_result, {'count': 0}).get('count', 0)
            # print(settings)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    # def get_partner_count():
    #     try:
    #         role_total = Partner.objects().count()
    #         return role_total
    #     except NotUniqueError as e:
    #         return '0' 
        
    def get_partner_details(id, partner_user, partner_id):
        try:
            
            filter = {}
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            # {'$lookup': app_config.countriesLookup},
                            # {'$lookup': app_config.statesLookup},
                            {'$match': match},
                            # {'$project': app_config.organization_project}
                       ]
            
            settings = defaultdict(list)
            role = Partner.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='_id':
                        assigned = item[item1]
                        users_count = AdminAPI.partner_users_count(assigned, partner_user, partner_id) 
                        users_count=Uid.fix_array(users_count)
                        settings['users_count'] = len(users_count)
                        
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date

                    if item1 == 'start_date' or item1 == 'end_date':
                        create_date1 = item[item1]
                        try:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        except ValueError:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)
                        
                        if item1 == 'start_date':
                            settings['start_date'] = create_date
                        elif item1 == 'end_date':
                            settings['end_date'] = create_date
                            settings['create_time'] = create_time

                  
                    else:
                        data = {item1:item4}
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def partner_update(id,data1):
        try:
            settings = defaultdict(list)
            settings['modify_date'] = datetime.datetime.utcnow
            data1['phone'] = str(data1.get('phone', ''))
            # print(data1,'genga')
            for data in data1:   
                settings[data] = data1[data]
                if data=='_id':
                    del settings[data]
            user = Partner.objects(id=ObjectId(id)).update_one(**settings)
            output = 'Yes'
        except Partner.DoesNotExist:
            output = 'No'   
        return output
    
    def partner_users_count(Id, partner_user, partner_id):
        try:
            # sData = int(page)*int(length)
            # length1 = int(page)-1
            # sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            filter['partner_id'] = Id
            # if search :
            #     filter1['name__contains'] = search
                # filter['name__contains'] = search
            # if status :
            #     filter['status'] = status
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                           
                            {'$match'  : match},
                           
                        ]
            
            settings = defaultdict(list)

            role = Partner_user.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='currency':
                        settings[item1] = item[item1]
                    # elif item1=='report':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings[item1] = item2['name']
                    
                    # if item1 == 'name':
                    #     name = item[item1]
                    #     if name:
                    #         first_letter = name[0].upper()
                    #         settings['user_FL'] = first_letter

                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    if item1=='plan_start_date':
                        start_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['start_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        start_date1 = start_date1 + timedelta(hours=offset)


                        plan_start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_start_date'] = plan_start_date
                        settings['start_time'] = start_time
                       
                    if item1=='plan_end_date':
                        end_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        end_date1 = end_date1 + timedelta(hours=offset)


                        plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_end_date'] = plan_end_date
                        settings['end_time'] = end_time
                       

                    if item1=='target_date':
                        target_date = item[item1]
                        target_date = datetime.datetime.strptime(str(target_date), DATE_FORMAT4).strftime(DATE_FORMAT1)
                        settings['target_date'] = target_date
                    else:
                        data = {item1:item4}
                    if not settings['report']:
                        settings['report']=''
                    if not settings['roleData']:
                        settings['roleData']=''
                    

                settings6.append(settings)
            
            settings2 = json.loads(json_util.dumps(settings6))
            # print(settings2,'1111111')
            return settings2
        except NotUniqueError as e:
            return '0'
        
    
    def create_partner_user(email,password,name,partner_id,phone,role,report_to,permissions):

        try:
            report_days=[]
            report_days.append('Monday')
            report_days.append('Tuesday')
            report_days.append('Wednesday')
            report_days.append('Thursday')
            report_days.append('Friday')
            report_days.append('Saturday')

            create_date = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            
            phone = str(phone)
            user = Partner_user(email=email,name=name,partner_id=partner_id,password=password,phone=phone,role=role,report_to=report_to,report_days=report_days,permissions=permissions,create_date=create_date)
            response = user.save()
            output1 = {'user_id' : str(response.id)}
            delete_report_to =  Reporting_To.objects(user_id=response.id).delete()
            # for report in report_to:
            #     insert_reporting = Reporting_To(user_id=response.id,reporting_to=report)
            #     insert_reporting_save = insert_reporting.save()
            return output1
        except NotUniqueError as e:
            return ''
        
    def get_partner_user_list(partner_user, partner_id):
        try:
           
            filter = {}
            # filter['status'] = "active"
            filter['partner_id'] = ObjectId(partner_id)
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='_id'
            order=1
            pipeline = [
                            # {'$lookup': app_config.user1_lookup},
                            # {'$lookup' : app_config.customer_type_lookup},
                            {"$sort": {sort: order}},
                            {'$match': match},
                            
                            # { '$project': app_config.company_project}
                        ]
            
            settings = defaultdict(list)    

            role = Partner_user.objects.aggregate(*pipeline)
            settings6=[]

            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    # if item1 == '_id':
                    #     partner_id = item[item1]

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date

                    if item1 == 'start_date' or item1 == 'end_date':
                        create_date1 = item[item1]
                        try:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        except ValueError:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)
                        
                        if item1 == 'start_date':
                            settings['start_date'] = create_date
                        elif item1 == 'end_date':
                            settings['end_date'] = create_date
                            settings['create_time'] = create_time

                       
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
        
    # def get_partner_user_count():
    #     try:
    #         role_total = Partner_user.objects().count()
    #         return role_total
    #     except NotUniqueError as e:
    #         return '0' 
        
    def get_partner_user_details(id, partner_user, partner_id):
        try:
            
            filter = {}
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            # {'$lookup': app_config.countriesLookup},
                            # {'$lookup': app_config.statesLookup},
                            {'$match': match},
                            # {'$project': app_config.organization_project}
                       ]
            
            settings = defaultdict(list)
            role = Partner_user.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    # elif item1=='countryId':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['country_id'] = item2['id']
                    # elif item1=='partner_id':
                    #     assigned = item[item1]
                    #     # admin_user = AdminAPI.getOrgUser(item[item1],item['email'])
                    #     admin_user=''
                    #     settings['admin_user']=admin_user
                    #     settings['no_of_users']=AdminAPI.get_partner_user_count(item[item1])
                    # elif item1=='stateId':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['state_id'] = item2['id']
                    # elif item1=='source_name':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['source_name'] = item2['name']
                    # elif item1=='customerType':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['customer_type_name'] = item2['name']

                    # if item1 == '_id':
                    #     partner_id = item[item1]
                        
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date

                    if item1 == 'start_date' or item1 == 'end_date':
                        create_date1 = item[item1]
                        try:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        except ValueError:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)
                        
                        if item1 == 'start_date':
                            settings['start_date'] = create_date
                        elif item1 == 'end_date':
                            settings['end_date'] = create_date
                            settings['create_time'] = create_time

                  
                    else:
                        data = {item1:item4}
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return '0'
        
        
    def partner_user_update(id,email,name,phone,role,permissions):
        try:
            modify_date = datetime.datetime.utcnow
            # partner_id = id
            user = Partner_user.objects(id=ObjectId(id)).update_one(email=email,name=name,phone=phone,role=role,permissions=permissions,modify_date=modify_date)
            output = 'Yes'
        except Partner_user.DoesNotExist:
            output = 'No'   
        return output
    
    def partner_user_status_update(id,status):
        try:
            response = Partner_user.objects(id=ObjectId(id)).update_one(status=status)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id
    
    
    # def get_admin_partner_org_list(partner_user, partner_id):
    #     try:
    #         filter = {}
    #         # filter['partner_id'] = ObjectId(partner_id)
            
    #         details = AdminAPI.get_partner_details(partner_id, partner_user, partner_id)
    #         details = Uid.fix_array3(details)

    #         key = []
    #         val = []

    #         for item1 in filter:
    #             key.append(item1)
    #             val.append(filter[item1])

    #         match = filter
    #         sort = '_id'
    #         order = -1
    #         pipeline = [
    #             {"$sort": {sort: order}},
    #             {'$match': match},
    #         ]

    #         settings = defaultdict(list)
    #         role = Organization.objects.aggregate(*pipeline)
    #         settings6 = []

    #         user_role = details.get('role', '')
    #         for item in role:
    #             if user_role == 'Partner' and 'partner_id' in item:
    #                 settings = defaultdict(list)
    #                 for item1 in item:
    #                     settings[item1] = item[item1]
    #                     item4 = str(item[item1])

    #                     if item1 == 'create_date':
    #                         create_date1 = item[item1]
    #                         offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
    #                         utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
    #                         settings['create_date_utc'] = utc_date
    #                         create_date1 = create_date1 + timedelta(hours=offset)
    #                         create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
    #                         create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
    #                         settings['create_date'] = create_date
    #                         settings['create_time'] = create_time
    #                         settings['date_aging'] = TokenRefresh.calculate_age(create_date)

    #                     if item1 == 'modify_date':
    #                         modify_date = item[item1]
    #                         offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
    #                         utc_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
    #                         modify_date = modify_date + timedelta(hours=offset)
    #                         create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
    #                         settings['modify_date'] = create_date

    #                     if item1 in ['start_date', 'end_date']:
    #                         create_date1 = item[item1]
    #                         try:
    #                             create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
    #                             create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
    #                         except ValueError:
    #                             create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
    #                             create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)

    #                         if item1 == 'start_date':
    #                             settings['start_date'] = create_date
    #                         elif item1 == 'end_date':
    #                             settings['end_date'] = create_date
    #                             settings['create_time'] = create_time
                    
    #                 settings6.append(settings)

    #             elif user_role == 'Admin':
    #                 settings = defaultdict(list)
    #                 for item1 in item:
    #                     settings[item1] = item[item1]
    #                     item4 = str(item[item1])

    #                     if item1 == 'create_date':
    #                         create_date1 = item[item1]
    #                         offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
    #                         utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
    #                         settings['create_date_utc'] = utc_date
    #                         create_date1 = create_date1 + timedelta(hours=offset)
    #                         create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
    #                         create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
    #                         settings['create_date'] = create_date
    #                         settings['create_time'] = create_time
    #                         settings['date_aging'] = TokenRefresh.calculate_age(create_date)

    #                     if item1 == 'modify_date':
    #                         modify_date = item[item1]
    #                         offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
    #                         utc_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
    #                         modify_date = modify_date + timedelta(hours=offset)
    #                         create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
    #                         settings['modify_date'] = create_date

    #                     if item1 in ['start_date', 'end_date']:
    #                         create_date1 = item[item1]
    #                         try:
    #                             create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
    #                             create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
    #                         except ValueError:
    #                             create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
    #                             create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)

    #                         if item1 == 'start_date':
    #                             settings['start_date'] = create_date
    #                         elif item1 == 'end_date':
    #                             settings['end_date'] = create_date
    #                             settings['create_time'] = create_time

    #                 settings6.append(settings)

    #         settings2 = json.loads(json_util.dumps(settings6))
    #         return settings2

    #     except NotUniqueError as e:
    #         return '0'


    def get_admin_partner_org_list(partner_user, partner_id):
        try:
            filter = {}
            # filter['partner_id'] = ObjectId(partner_id)
            
            details = AdminAPI.get_partner_details(partner_id, partner_user, partner_id)
            details = Uid.fix_array3(details)
            partner_role = details.get('role', '')
            if partner_role=="Partner":
                print(partner_role)
                filter['partner_id'] = ObjectId(partner_id)
                
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])

            match = filter
            sort = '_id'
            order = -1
            pipeline = [
                {"$sort": {sort: order}},
                {'$match': match},
            ]

            settings = defaultdict(list)
            role = Organization.objects.aggregate(*pipeline)
            settings6 = []

            # user_role = details.get('role', '')
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1 == 'create_date':
                        create_date1 = item[item1]
                        offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
                        utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date
                        create_date1 = create_date1 + timedelta(hours=offset)
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)

                    if item1 == 'modify_date':
                        modify_date = item[item1]
                        offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
                        utc_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        modify_date = modify_date + timedelta(hours=offset)
                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        settings['modify_date'] = create_date

                    if item1 in ['start_date', 'end_date']:
                        create_date1 = item[item1]
                        try:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        except ValueError:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)

                        if item1 == 'start_date':
                            settings['start_date'] = create_date
                        elif item1 == 'end_date':
                            settings['end_date'] = create_date
                            settings['create_time'] = create_time
                
                settings6.append(settings)

                    # settings6.append(settings)

            settings2 = json.loads(json_util.dumps(settings6))
            return settings2

        except NotUniqueError as e:
            return '0'




    # def get_admin_org_count():
    #     try:
    #         role_total = Organization.objects().count()
    #         return role_total
    #     except NotUniqueError as e:
    #         return '0' 
        
    def search_admin_partner_org_list(partner_id, current_user, search_string):
        try:
            # match ={}
            # match['assigned_to'] = {'$in': [ObjectId(current_user)]}
            # print(match,'mmmmmmmmmmmmmm')
            

            pipeline = [
                # {'$match': match},
                {'$match':{
                    '$or': [
                    {'organization_name': { "$regex": search_string, "$options" :'i'}}, 
                    {'phone': { "$regex": search_string, "$options" :'i'}}, 
                    {'email': { "$regex": search_string, "$options" :'i'}},
                    {'status': { "$regex": search_string, "$options" :'i'}},
                    {'create_date': { "$regex": search_string, "$options" :'i'}}, 
                    ],         
                }},
                #  {'$lookup': app_config.task_priority_lookup},
            ]

            tasks = Organization.objects.aggregate(*pipeline)
            # print(str(tasks),pipeline,'str')
            settings6 = []
            for item in tasks:
                # print(item,'iiiiiiiii')
                settings = defaultdict(list)
                for item1 in item:
                    # settings = defaultdict(list)
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(current_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)

                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    
                    if item1=='due_date':
                        due_date = item[item1] 

                        # print(target_date)
                        create_date = datetime.datetime.strptime(str(due_date), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        # create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        # create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['due_date'] = create_date

                    
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            # total_count = next(count_result, {'count': 0}).get('count', 0)
            # print(settings)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def get_admin_org_detail(id,partner_user, partner_id):
        try:
           
            filter = {}
            # filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            
            pipeline = [
                            # {'$lookup': app_config.company_status_lookup},
                            # {'$lookup' : app_config.partner_name},
                            # {'$lookup' : app_config.Plan_type},
                            # {'$lookup': app_config.user_lookup},
                            {'$match': match},
                            
                            # { '$project': app_config.company_project}
                        ]
            
            settings = defaultdict(list)

           

            role = Organization.objects.aggregate(*pipeline)
            settings6=[]
            
            # item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='partner_id':
                        assigned = item[item1]
                        partner_details=AdminAPI.get_partner_details(partner_id, partner_user, partner_id)
                        partner_details=Uid.fix_array3(partner_details)
                        settings['partner_name'] = partner_details.get('name', '')
                    elif item1=='plan_id':
                        assigned = item[item1]
                        plan_details=MongoAPI.getPlansListDetails(assigned)
                        plan_details=Uid.fix_array3(plan_details)
                        settings['plan_name'] = plan_details.get('plan_name', '')
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    if item1=='plan_start_date':
                        start_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['start_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        start_date1 = start_date1 + timedelta(hours=offset)


                        plan_start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_start_date'] = plan_start_date
                        settings['start_time'] = start_time

                    if item1=='plan_end_date':
                        end_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        end_date1 = end_date1 + timedelta(hours=offset)


                        plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_end_date'] = plan_end_date
                        settings['end_time'] = end_time
                       
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                            settings['mail_signature'] = item2['mail_signature']
                    elif item1=='teams':
                        teams = item[item1]
                        teams= [str(data) for data in teams]
                        settings['teams']=teams                

               
            settings2 = json.loads(json_util.dumps(settings))
            
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def org_user_update(email,name,phone,id,plan_start_date,plan_end_date,status,report_to):
        try:
            modify_date = datetime.datetime.utcnow
            user_id = id
            user = User.objects(id=id).update_one(email=email,name=name,phone=phone,plan_start_date=plan_start_date,plan_end_date=plan_end_date,status=status,report_to=report_to)
            delete_report_to =  Reporting_To.objects(user_id=id).delete()
            # for report in report_to:
            #     insert_reporting = Reporting_To(user_id=id,reporting_to=report)
            #     insert_reporting_save = insert_reporting.save()
            output = 'Yes'
        except User.DoesNotExist:
            output = 'No'   
        return output
        

    def UsersNewListGet(ordId, partner_user, partner_id):
        try:
            # sData = int(page)*int(length)
            # length1 = int(page)-1
            # sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            filter['org_id'] = ordId
            # if search :
            #     filter1['name__contains'] = search
                # filter['name__contains'] = search
            # if status :
            #     filter['status'] = status
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            # {'$lookup' : app_config.report_to_lookup},
                            {'$lookup' : app_config.role_lookup},
                            # {'$lookup' : app_config.department_lookup},
                            # {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            # {'$match':{
                            #     '$or': [
                            #     {'name': { "$regex": search, "$options" :'i'}}, 
                            #     {'email': { "$regex": search, "$options" :'i'}},
                            #     ],
                            # }},
                            # {'$skip'   : sData1},
                            # {'$limit'  : length},
                            # {'$project': app_config.user_project}
                        ]
            
            settings = defaultdict(list)

            role = User.objects(**filter1).aggregate(*pipeline)
            # print(pipeline,'hhhhh')
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='currency':
                        settings[item1] = item[item1]
                    # elif item1=='report':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings[item1] = item2['name']
                    # elif item1=='report_to':
                    #     settings['reporting_to']=[] 
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                            
                    #         this_user=MongoAPI.getUserDetails(ordId,item2)
                    #         # this_user2 = Uid.fix_array3(this_user)
                    #         settings['reporting_to'].append(this_user)
                    elif item1=='roleData':
                        assigned = item[item1]
                        assignedLen = len(list(assigned))
                        if assignedLen:
                            for item2 in assigned:
                                # print (assigned)
                                settings['roleData'] = item2['role_name']
                    # elif item1=='deptData':
                    #     assigned = item[item1]
                    #     assignedLen = len(list(assigned))
                    #     if assignedLen:
                    #         for item2 in assigned:
                    #             # print (assigned)
                    #             settings['deptData'] = item2['department_name']
                        # else:
                        #     settings['roleData'] = ''
                    if item1 == 'name':
                        name = item[item1]
                        if name:
                            first_letter = name[0].upper()
                            settings['user_FL'] = first_letter

                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    if item1=='plan_start_date':
                        start_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['start_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        start_date1 = start_date1 + timedelta(hours=offset)


                        plan_start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_start_date'] = plan_start_date
                        settings['start_time'] = start_time
                       
                    if item1=='plan_end_date':
                        end_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        end_date1 = end_date1 + timedelta(hours=offset)


                        plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_end_date'] = plan_end_date
                        settings['end_time'] = end_time
                       

                    if item1=='target_date':
                        target_date = item[item1]
                        target_date = datetime.datetime.strptime(str(target_date), DATE_FORMAT4).strftime(DATE_FORMAT1)
                        settings['target_date'] = target_date
                    else:
                        data = {item1:item4}
                    if not settings['report']:
                        settings['report']=''
                    if not settings['roleData']:
                        settings['roleData']=''
                    

                settings6.append(settings)
            
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def update_admin_org_detail(org_id,partner_user,data1,id):
        try:
            
            settings = defaultdict(list)
            settings['modify_date'] = datetime.datetime.utcnow
            # print(data1,'genga')
            for data in data1:   
                settings[data] = data1[data]
                if data=='_id':
                    del settings[data]
            # print(settings,'111genga')
            response = Organization.objects(org_id=org_id).update_one(**settings)
            output1 = str(id)
            return output1
        except NotUniqueError as e:
            return '0'
    
    def admin_org_status(status,id,org_id):
        try:
            modify_date = datetime.datetime.utcnow
            user_id = id
            user = Organization.objects(org_id=org_id).update_one(status=status)
            output = 'Yes'
        except User.DoesNotExist:
            output = 'No'   

        return output

    def orgcontactSubmit(org_id,user_id,data1):
        try:
            data1['create_by'] = user_id
            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            data1['org_id'] = org_id
            data1['phone'] = str(data1.get('phone', ''))
            data1['alt_phone'] = str(data1.get('alt_phone', ''))

            u2 = Admin_contacts.from_json(json.dumps(data1))
            u2.save()
            output1 = str(u2.id)
            return output1
        except NotUniqueError as e:
            return '0' 
        
    def get_org_contact_Details(partner_id,id,partner_user):
        try:
            filter = {}
            # filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            
            pipeline = [      
                            {'$match': match}                           
                        ]
            
            settings = defaultdict(list)

            role = Admin_contacts.objects.aggregate(*pipeline)
            settings6=[]
            
            item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    
            settings2 = json.loads(json_util.dumps(settings))
            
            return settings2
        except NotUniqueError as e:
            return '0'

    def org_contact_update(org_id,partner_user,data1,id):
        try:
            
            settings = defaultdict(list)
            settings['modify_date'] = datetime.datetime.utcnow

            data1['phone'] = str(data1.get('phone', ''))
            data1['alt_phone'] = str(data1.get('alt_phone', ''))
            # print(data1)
            for data in data1:

                
                settings[data] = data1[data]
                if data=='_id':
                    del settings[data]
            response = Admin_contacts.objects(org_id=org_id,id=ObjectId(id)).update_one(**settings)
            output1 = str(id)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def org_associate_contactList(org_id,partner_user,partner_id):
        try:
           
            filter = {}
            filter['org_id'] = org_id
            # filter['company_id'] = ObjectId(company_id)
            
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='_id'
            order=-1
            pipeline = [
                            {"$sort": {sort: order}},
                            {'$match': match},
                        ]
            
            settings = defaultdict(list)

           

            role = Admin_contacts.objects.aggregate(*pipeline)
            settings6=[]
            # print(pipeline)
            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                       
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'

    def deleteorg_contact(id):

        user = Admin_contacts.objects(id=id).first()
        if not user:
            return 'No'
        else:
            user.delete()
            return 'Yes'
        
    def org_contact_Default(org_id,id,default=0):
        try:
            data5 = defaultdict(list)
            data5['default'] = 0
            Admin_contacts.objects(org_id=org_id).update(**data5)


            data6 = defaultdict(list)
            data6['default'] = 1
            Admin_contacts.objects(id=ObjectId(id)).update_one(**data6)

            # u2.save()
            output1 = id
            return output1
        except NotUniqueError as e:
            return '0'
        
    def org_profile_get(id):
        # try:
        #     s = User.objects.filter(id=id).to_json()
        #     output = json.loads(s)
           
        # except NotUniqueError as e:
        #     output = ''
        # return output
        try:
            filter = {}
            # filter['org_id'] = ordId   
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [    {'$lookup' : app_config.role_lookup},
                            {'$match': match}
                        ]
            settings = defaultdict(list)
            # print (pipeline)
            role = Partner_user.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    if item1=='role':
                        assigned = item[item1]
                        settings['role']=str(assigned)
                    if item1=='tax_type':
                        assigned = item[item1]
                        settings['tax_type']=str(assigned)

                    if item1=='_id':
                        item3 = item[item1]
                        settings['_id']=str(item3)
                    if item1=='user_id':
                        item3 = item[item1]
                        settings['user_id']=str(item3)
                        # for items in item3:
                        #     settings['_id']=str(items['$oid'])
                     
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    else:
                        data = {item1:item4}            
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return 'No'
        
    def org_profile_Update(id,name,phone,role):
        try:
            response = Partner_user.objects(id=id).update_one(name=name,phone=phone,role=role)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id
        
    def partnerInfo(partner_id):
        try:
            organization_data = Partner.objects.filter(id=partner_id).first()
            if organization_data:
                currency_list = []
                organization = json.loads(organization_data.to_json())
                # Fetch currency names from Currencies table based on _id
                currency_ids = organization.get('currency', [])
                if currency_ids:
                    for currency_id in currency_ids:
                        try:
                            currency = Currencies.objects.get(id=currency_id)
                            currency_name = currency.name
                            currency_id = str(currency.id)
                            currency_list.append({'currency_name': currency_name, 'currency_id': currency_id})
                        except Currencies.DoesNotExist:
                            # Handle the case where the currency does not exist
                            continue
                organization['currency_list'] = currency_list
            else:
                organization = {}
        except Organization.DoesNotExist:
            organization = {}
        return organization
    
    def update_partner_User_Logo(id,profile_image):
        try:
            response = Partner_user.objects(id=id).update_one(profile_image=profile_image)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id
    
    def settingsall(type):
        if type=='timezones':
            try:
                s = Timezones.objects.filter().to_json()
                output = json.loads(s)
                # print (output)
                return output
            except s.DoesNotExist:
                return '0'
            
        elif type=='currency':
            try:
                s = Currencies.objects.filter().to_json()
                output = json.loads(s)
                return output
            except s.DoesNotExist:
                return '0'
            
        elif type=='country':
            try:
                s = Countries.objects.filter().to_json()
                output = json.loads(s)
                return output
            except s.DoesNotExist:
                return '0'
            
        # elif type=='date_format':
        #     try:
        #         s = Currencies.objects.filter().to_json()
        #         output = json.loads(s)
        #         return output
        #     except s.DoesNotExist:
        #         return '0'
        
        # elif type=='amc_status':
        #     try:
        #         s = Countries.objects.filter().to_json()
        #         output = json.loads(s)
        #         return output
        #     except s.DoesNotExist:
        #         return '0'

    def getpartner_user_Password(user_id):
        try:
            s = Partner_user.objects.filter(id=ObjectId(user_id)).to_json()
            output = json.loads(s)
        except User.DoesNotExist:
            output = 'No'   

        return output

    def partner_user_Password(user_id,password):
        try:
            modify_date = datetime.datetime.utcnow
            user = Partner_user.objects(id=user_id).update_one(password=password)
            output = 'Yes'
        except User.DoesNotExist:
            output = 'No'   

        return output 
    
    def partner_regionalSettings_Update(id,currency,time_zone):
        try:
            modify_date = datetime.datetime.utcnow
            
 
            user = Partner_user.objects(id=id).update_one(currency=currency,time_zone=time_zone,modify_date=modify_date)
            output = 'Yes'
        except User.DoesNotExist:
            output = 'No'   
        return output
    
    def get_org_user_details(id, partner_user, partner_id):

        try:
            filter = {} 
            # filter['org_id'] = ordId
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$match': match},
                            # {'$lookup': app_config.role_user_lookup}
                        ]
            settings = defaultdict(list)
            print (pipeline,'nnnnnnnnnnnnnnnn')
            role = User.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    # elif item1=='role_name':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    if item1=='role':
                        assigned = item[item1]
                        settings['role']=str(assigned)
                    if item1=='dashboard_favorites':
                        dashboard_favorites = item[item1]
                        # print(dashboard_favorites,'ooooo')
                        dashboard_favorites_data=[]
                        for d_f in dashboard_favorites:
                            dashboard_favorites_data.append(str(d_f))
                        settings['dashboard_favorites']=dashboard_favorites_data
                            
                    # if item1=='department':
                    #     assigned = item[item1]
                    #     settings['department']=str(assigned)
                     
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    if item1=='plan_start_date':
                        start_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['start_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        start_date1 = start_date1 + timedelta(hours=offset)


                        plan_start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_start_date'] = plan_start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    if item1=='plan_end_date':
                        end_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        end_date1 = end_date1 + timedelta(hours=offset)


                        plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_end_date'] = plan_end_date
                        settings['end_time'] = end_time
                        settings['date_aging'] = TokenRefresh.calculate_age(end_date2)
                    else:
                        data = {item1:item4}            
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return 'No'
        
        
    def get_partner_plans_List(length,page,search,sort,order):
        try:
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            # filter['org_id'] = ordId
            # if search :
            #     filter1['plan_name__contains'] = search
                # filter['name__contains'] = search
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            # fields_lookup = {'from': 'product','startWith':'$product_name','connectFromField': 'product','connectToField': '_id','maxDepth':50,'as': 'product_data'}
            pipeline = [
                            # {'$lookup' : app_config.ownerLookup},
                            {'$sort'   : {sort : order}},
                            {'$match'  : match}
                        ]
           
            settings = defaultdict(list)

            role = Plan_wise_modules.objects(**filter1).aggregate(*pipeline)

            settings6=[]
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                # print (item)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    if item1=='valid_till':
                        valid_till = item[item1]
                        valid_till = datetime.datetime.strptime(str(valid_till), DATE_FORMAT4).strftime(DATE_FORMAT1)
                        settings['valid_till'] = valid_till
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''
                settings6.append(settings)
            
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def partner_plans_details(id,partner_user,partner_id):
        try:
           
            filter = {}
            filter['_id'] = id
            # filter['company_id'] = ObjectId(company_id)
            
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='_id'
            order=-1
            pipeline = [
                            {"$sort": {sort: order}},
                            {'$match': match},
                        ]
            
            settings = defaultdict(list)

           

            role = Plan_wise_modules.objects.aggregate(*pipeline)
            settings6=[]
            
            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                       
                # settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings))
            print(pipeline)
            return settings2
        except NotUniqueError as e:
            return '0'
        
        
    def checkSettings(type,name,partner_id):
        try:
            
            fields = Admin_fields.objects.get(type=type,name=name,partner_id=ObjectId(partner_id))
            if fields.name:
                output = 'Yes'
            else:
                output = 'No'
            return output
        except Admin_fields.DoesNotExist:
            return 'No'
        
    def fieldsSettingsCount(type,partner_id):
        try:
                      
            count = Admin_fields.objects.filter(type=type,partner_id=ObjectId(partner_id)).count()
        
            return count
        except Admin_fields.DoesNotExist:
            return '0'
        
    def partner_fields_settings_data(type,partner_id):
        try:
            s = Admin_fields.objects.filter(type=type,partner_id=ObjectId(partner_id)).order_by('sort_order').to_json()
            output = json.loads(s)
            stage_list=[]
            if type=='deal_stage':
                for ds in output:
                    # print(ds)
                    if ds['name']!='Revised':
                        stage_list.append(ds)
            else:
                stage_list=output
            # print(stage_list)
            return stage_list
        except Admin_fields.DoesNotExist:
            return '0'
        
    def addleadsettings(type,name,info,partner_id,count,default=0,color=''):
        try:
            count = int(count)+1

            if default==1:
                user = Admin_fields.objects(type=type,partner_id=ObjectId(partner_id)).update(default=0)

            create_date = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            
            if count==1:
                fields = Admin_fields(type=type,name=name,partner_id=ObjectId(partner_id),sort_order=count,default=1,info=info,color=color,create_date=create_date)
            else:
                fields = Admin_fields(type=type,name=name,partner_id=ObjectId(partner_id),sort_order=count,default=default,info=info,color=color,create_date=create_date)

            response = fields.save()

            output1 = {'field_id' : response.id}

            return output1
        except Admin_fields.DoesNotExist:
            return ''
        
    def settingsData(type, partner_id):
        try:
            filter = {}
            key = []
            val = []
            filter['partner_id'] = ObjectId(partner_id)
         
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='sort_order'
            order=1

            pipeline = [
                            {'$lookup': app_config.settingsLookup},
                            {'$match': match},
                            {"$sort": {sort: order}},
                        ]
            # print(pipeline,'jjjjjjjjjjjj')
            role = Admin_fields.objects.filter(type=type, partner_id=partner_id).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    if item1=='date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        settings['date'] = create_date
                    # if item1=='attachment':
                    #     attachment1 = item[item1]
                    #     attachment = []
                    #     for item3 in attachment1:
                    #         attachment2 = str(app_config.BASE_URL)+str(app_config.UPLOAD_OPEN_EMAIL_FOLDER)+str(item3)
                    #         attachment.append(attachment2)
                    #     settings['attachment'] = attachment
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''



                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def leadsettings_detail(id,partner_id):

        try:
            filter = {}
            filter['partner_id'] = ObjectId(partner_id)
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$match': match}
                        ]
            settings = defaultdict(list)
            # print (pipeline,'nnnnnnnnnnnnnnnn')
            role = Admin_fields.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    # if item1=='assigned':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings[item1] = item2['name']
                    # elif item1=='account':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['company_name'] = item2['company_name']
                    # elif item1=='countryId':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['country_id'] = item2['id']
                    # elif item1=='stateId':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['state_id'] = item2['id']
                    # elif item1=='source_name':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings['source_name'] = item2['name']
                    # if item1=='role':
                    #     assigned = item[item1]
                    #     settings['role']=str(assigned)
                    # if item1=='department':
                    #     assigned = item[item1]
                    #     settings['department']=str(assigned)
                     
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    else:
                        data = {item1:item4}            
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return 'No'
        
    def updateleadsettings(partner_id,name,id,type,default,info,color):
        try:
            modify_date = datetime.datetime.utcnow
            if default==1:
                user = Admin_fields.objects(type=type,partner_id=ObjectId(partner_id)).update(default=0)
            
            user = Admin_fields.objects(id=id).update_one(name=name,modify_date=modify_date,default=default,info=info,color=color)
            output = 'Yes'
            output1 = {'id' : id}
            return output1
        except Admin_fields.DoesNotExist:
            return ''
        
    def lead_settingsDefault(type,partner_id,id):
        try:
            data5 = defaultdict(list)
            data5['default'] = 0
            Admin_fields.objects(partner_id=ObjectId(partner_id),type=type).update(**data5)


            data6 = defaultdict(list)
            data6['default'] = 1
            Admin_fields.objects(id=ObjectId(id)).update_one(**data6)

            # u2.save()
            output1 = id
            return output1
        except NotUniqueError as e:
            return '0'
        
    def deleteleadSettings(id):

        user = Admin_fields.objects(id=id).first()
        if not user:
            return 'No'
        else:
            user.delete()
            return 'Yes'
        

    def admin_leadSubmit(partner_id, user_id, data1):
        try:
            # Adding required fields to data1
            data1['create_by'] = user_id
            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            data1['partner_id'] = partner_id
            # print(data1, 'Processed Data')

            # Extract optional fields
            contact_name = data1.pop('contact_name', None)
            phone = data1.pop('phone', None)
            email = data1.pop('email', None)

            # Create and save the lead object
            u2 = Admin_lead.from_json(json.dumps(data1))
            u2.save()

            # Retrieve the lead ID
            lead_id = str(u2.id)

            # If contact details exist, submit them
            if contact_name:
                contact_data = {
                    "contact_name": contact_name,
                    "phone": phone,
                    "email": email,
                    "lead_id": lead_id
                }
                print(contact_data, 'Contact Data')
                AdminAPI.leadcontactSubmit(lead_id, user_id, contact_data)

            return lead_id

        except NotUniqueError as e:
            return '0'
        

    def getadmin_lead(partner_user, partner_id):
        try:
            filter = {}
            filter1 = {}
            key = []
            val = []
            filter['partner_id'] = ObjectId(partner_id)

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$match'  : match},
                            {'$lookup' : app_config.partner_lead_status_lookup},
                            {'$lookup': app_config.partner_user_lookup},
                        ]
            
            settings = defaultdict(list)

            role = Admin_lead.objects(**filter1).aggregate(*pipeline)
            # print(pipeline,'hhhhhh')
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}

                    if item1=='assigned':
                        
                        assigned = item[item1]
                        # print(assigned,'1111111')
                        for item2 in assigned:
                            settings['assigned_to'] = item2['name']

                    elif item1=='lead_status_name':
                        
                        assigned = item[item1]
                        # print(assigned,'22222222')
                        for item2 in assigned:
                            settings['lead_status_name'] = item2['name']
                            settings['lead_status_color'] = item2['color']

                    if item1 == 'create_date':
                            create_date1 = item[item1]
                            offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
                            utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                            settings['create_date_utc'] = utc_date
                            create_date1 = create_date1 + timedelta(hours=offset)
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                            settings['create_date'] = create_date
                            settings['create_time'] = create_time
                            settings['date_aging'] = TokenRefresh.calculate_age(create_date)

                    if item1 == 'modify_date':
                        modify_date = item[item1]
                        offset = AdminAPI.partnercommontimeset(partner_user, partner_id)
                        utc_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        modify_date = modify_date + timedelta(hours=offset)
                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        settings['modify_date'] = create_date

                    if item1 in ['start_date', 'end_date']:
                        create_date1 = item[item1]
                        try:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        except ValueError:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)

                        if item1 == 'start_date':
                            settings['start_date'] = create_date
                        elif item1 == 'end_date':
                            settings['end_date'] = create_date
                            settings['create_time'] = create_time
                    else:
                        data = {item1:item4}
                    if not settings['report']:
                        settings['report']=''
                    if not settings['roleData']:
                        settings['roleData']=''
                    

                settings6.append(settings)
            
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def get_admin_lead_detail(id,partner_user, partner_id):
        try:
           
            filter = {}
            # filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            
            pipeline = [
                            # {'$lookup': app_config.company_status_lookup},
                            # {'$lookup' : app_config.partner_name},
                            # {'$lookup' : app_config.Plan_type},
                            # {'$lookup': app_config.user_lookup},
                            {'$match': match},
                            {'$lookup' : app_config.partner_lead_status_lookup},
                            {'$lookup': app_config.partner_user_lookup},
                            
                            # { '$project': app_config.company_project}
                        ]
            
            settings = defaultdict(list)

           

            role = Admin_lead.objects.aggregate(*pipeline)
            settings6=[]
            # print(pipeline,'pppppppppppp')
            # item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    # print(settings,'dfgdfg')
                    # if item1=='partner_id':
                    #     assigned = item[item1]
                    #     partner_details=AdminAPI.get_partner_details(partner_id, partner_user, partner_id)
                    #     partner_details=Uid.fix_array3(partner_details)
                    #     settings['partner_name'] = partner_details.get('name', '')
                    # elif item1=='plan_id':
                    #     assigned = item[item1]
                    #     plan_details=MongoAPI.getPlansListDetails(assigned)
                    #     plan_details=Uid.fix_array3(plan_details)
                    #     settings['plan_name'] = plan_details.get('plan_name', '')
                    if item1=='assigned':      
                        assigned = item[item1]
                        # print(assigned,'1111111')
                        for item2 in assigned:
                            settings['assigned_to'] = item2['name']

                    elif item1=='lead_status_name':   
                        assigned = item[item1]
                        # print(assigned,'22222222')
                        for item2 in assigned:
                            settings['lead_status_name'] = item2['name']
                            settings['lead_status_color'] = item2['color']

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    if item1=='plan_start_date':
                        start_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['start_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        start_date1 = start_date1 + timedelta(hours=offset)


                        plan_start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_start_date'] = plan_start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    if item1=='plan_end_date':
                        end_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        end_date1 = end_date1 + timedelta(hours=offset)


                        plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_end_date'] = plan_end_date
                        settings['end_time'] = end_time
                        settings['date_aging'] = TokenRefresh.calculate_age(end_date2)
                    # if item1=='assigned':
                    #     assigned = item[item1]
                    #     for item2 in assigned:
                    #         settings[item1] = item2['name']
                    #         settings['assigned_to'] = item2['name']
                    # elif item1=='teams':
                    #     teams = item[item1]
                    #     teams= [str(data) for data in teams]
                    #     settings['teams']=teams                

               
            settings2 = json.loads(json_util.dumps(settings))
            
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def update_admin_lead_detail(partner_user,data1,id):
        try:
            
            settings = defaultdict(list)
            settings['modify_date'] = datetime.datetime.utcnow
            
            data1['pcode'] = str(data1.get('pcode', ''))
            
            # print(data1,'genga')
            for data in data1:   
                settings[data] = data1[data]
                if data=='_id':
                    del settings[data]
            # print(settings,'111genga')
            response = Admin_lead.objects(id=ObjectId(id)).update_one(**settings)
            output1 = str(id)
            return output1
        except NotUniqueError as e:
            return '0'
        

    def getNotes(partner_id,partner_user,id,associate_to,sort,order):
        try:
            filter = {}
            key = []
            val = []
            filter['partner_id'] = ObjectId(partner_id)
            
            if id :
                filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to           
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                            {'$lookup': app_config.note_lookup},
                            {'$sort'   : {sort_by : order_dict}},
                            {'$match': match},
                            # { '$project': app_config.note_Project}
                        ]
            role = Admin_notes.objects.aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']='' 
                settings['type']='note' 
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            # settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def getEmail(partner_id,partner_user,id,associate_to,sort,order):
        try:
            filter = {}
            key = []
            val = []
            filter['partner_id'] = ObjectId(partner_id)
            if id :
                filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to

            
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']


            pipeline = [
                            {'$lookup': app_config.ownerLookup},
                            {'$match': match},
                            {'$sort'   : {sort_by : order_dict}},
                            # {'$project': app_config.email_Project}
                        ]

            

            role = Admin_email.objects.aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                    if item1=='date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        settings['date'] = create_date
                    if item1=='attachment':
                        attachment1 = item[item1]
                        attachment = []
                        for item3 in attachment1:
                            attachment2 = str(app_config.BASE_URL)+str(app_config.UPLOAD_OPEN_EMAIL_FOLDER)+str(item3)
                            attachment.append(attachment2)
                        settings['attachment'] = attachment
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''


                settings['type']='email' 
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            # settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def getDocument(partner_id,partner_user,id,associate_to,sort,order):
        try:
            filter = {}
            key = []
            val = []
            filter['partner_id'] = ObjectId(partner_id)
            
            if id :
                filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to           
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                            {'$lookup': app_config.note_lookup},
                            {'$match': match},
                            {'$sort'   : {sort_by : order_dict}},
                            # { '$project': app_config.document_Project}
                        ]
            role = Admin_document.objects.aggregate(*pipeline)
            # print("llooo",pipeline,"--------")
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='document':
                        attachment2 = str(app_config.BASE_URL)+str(app_config.UPLOAD_OPEN_DOCUMENT_FOLDER)+str(item[item1])
                        settings['document'] = attachment2
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                        
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']='' 
                settings['type']='document' 
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def documentSubmit(partner_id,partner_user,id,associate_to,document,user_file_name):
        try:
            shopping_list = []
            settings = defaultdict(list)
            data1 = defaultdict(list)

            data1['associate_id'] = id
            data1['associate_to'] = associate_to
            data1['user_id'] = partner_user
            data1['partner_id'] = partner_id
            data1['document_id'] = Uid.generateUUID()
            data1['document'] = document
            data1['create_by'] = partner_user
            data1['user_file_name'] = user_file_name
            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')

            for data in data1:
                # print (data)
                # shopping_list.append(data:data1[data])
                settings[data] = data1[data]
                
            # print("ooopppll",data1,"dataprint") 
            u2 = Admin_document.from_json(json.dumps(data1))
            u2.save()
            response = u2
            output1 = str(response.id)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def noteSubmit(partner_id,user_id,data1):
        try:
            print(data1,"kumar1111")
            settings = defaultdict(list)

            data1['create_by'] = user_id
            data1['partner_id'] = partner_id
            data1['note_id'] = Uid.generateUUID()

            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')

            for data in data1:
                settings[data] = data1[data]
            print(data1,"hhghghghg")
            u2 = Admin_notes.from_json(json.dumps(data1))
           
            u2.save()
            response = u2
            output1 = str(response.id)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def emailSubmit(partner_id,user_id,data1,emailId,attachment):
        try:
            # print(org_id,"222")
            # print(user_id,"ooii")
            # print (data1,"kkt")
            # print (emailId,"///")
            # print(attachment,"mmbb")
            shopping_list = []
            insertData = defaultdict(list)
            
            to_list = data1['to'].split(',')
            # print(to_list)
            data2=json.loads(json_util.dumps(data1))
            # print(data2,"99999")
            # if hasattr(data2,'cc'):
            # print('------------------------------------------')
            if data2['cc'] != '':
                cc_list = data2['cc'].split(',')
                data2['cc'] = cc_list
                
            else:
                cc_list = [] 
                data2['cc'] = []
            # else:
            #     cc_list = []
            
            # if hasattr(data2,'bcc'):
            if data2['bcc'] !='':
                bcc_list = data2['bcc'].split(',')
                data2['bcc'] = bcc_list
            else:
                bcc_list = []
                data2['bcc'] = []
            # else:
            #     bcc_list = []
            # print('response',"lllllll")  
            insertData['email_id'] = Uid.generateUUID()
            insertData['partner_id'] = partner_id
            insertData['email_type'] = 'bulk'
            insertData['fromEmail'] = emailId
            insertData['to'] = to_list
            insertData['cc'] = cc_list
            insertData['bcc'] = bcc_list
            insertData['subject'] = data1['subject']
            insertData['content'] = data1['content']
            insertData['attachment'] = attachment.split(",")
            insertData['associate_to'] =  data1['associate_to']
            insertData['associate_id'] =  data1['associate_id']
            insertData['create_by'] =  user_id
            insertData['create_date']=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            # print(insertData,'pppppppppppppp')
            
            u2 = Admin_email.from_json(json.dumps(insertData))
            u2.save()
            response = u2
            
            output1 = str(response.id)
            # print(output1)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def get_admin_Email_detail(partner_id,partner_user,id):
        try:
           
            filter = {}
            filter['partner_id'] = ObjectId(partner_id)
            filter['_id'] = ObjectId(id)
            
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
           
            pipeline = [
                            # {'$lookup': app_config.user1_lookup},
                            # {'$lookup' : app_config.customer_type_lookup},
                            # {'$lookup' : app_config.contact_type_lookup},
                            
                            {'$match': match},
                            
                            # { '$project': app_config.company_project}
                        ]
            
            settings = defaultdict(list)

           

            role = Admin_email.objects.aggregate(*pipeline)
            settings6=[]
            # print(pipeline)
            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)

                # settings6.append(settings)
            # if 'email_type' in settings:
            #     email_type = settings['email_type']
            #     fromEmail = settings.get('fromEmail','')
            #     thread_id = settings.get('thread_id','')
            #     if email_type=='single':
            #         acces_tokendetail=MongoAPI.users_gmailldetail_byemail(org_id,current_user,fromEmail)
            #         # print(to, subject,acces_tokendetail)
            #         refresh_token_encryped=acces_tokendetail.get('refresh_token','')
            #         sender_mail=acces_tokendetail.get('email','')            
                    
            #         # access_token=MongoAPI.decrypt_token(access_token_encryped)
            #         hashed_token_bytes = refresh_token_encryped.encode('utf-8')  # Convert UTF-8 string to bytes
            #         decoded_token_bytes = base64.b64decode(hashed_token_bytes)  # Decode base64 to bytes
            #         refresh_token = decoded_token_bytes.decode('utf-8')    
            #         print(refresh_token,'hjgg')  
            #         access_token=MongoAPI.refresh_access_token(refresh_token)

            #         email_threads=[]
            #         email_threads=MongoAPI.read_thread_mails(access_token, thread_id)
            #         print(email_threads,'ggggggggggg')
            #         settings['thread_data']=email_threads
                    
            settings2 = json.loads(json_util.dumps(settings))
            # print(settings2,'ssssssssssss')
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def delete_admin_lead_doc(id):

        user = Admin_document.objects(id=id).first()
        if not user:
            return 'No'
        else:
            user.delete()
            return 'Yes'
        
    def getTimeline(partner_id,partner_user,id,associate_to,sort,order):
        try:   
            # user=MongoAPI.authorizationCheck(current_user)
     
            filter = {}
            key = []
            val = []
            # filter['org_id'] = ordId
            # filter['associate_id'] = ObjectId(id)
            # filter['associate_to'] = associate_to

            filter['partner_id'] = ObjectId(partner_id)
            
            if id :
                filter['associate_id'] = ObjectId(id)
                # filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to   

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                            # {'$sort'   : {sort : order}},
                            {'$sort'   : {sort_by : order_dict}},
                            {'$lookup': app_config.partner_timelineLookup},
                            {'$match': match},
                            # {'$project': app_config.activity_Project_new}
                        ]
            # print (pipeline)
            settings = defaultdict(list)

            role = Admin_activity.objects.aggregate(*pipeline)
            # print("assssssssssssssssssssssassassa")
            # print (role)
            settings6=[]
            for item in role:
                settings = defaultdict(list)      
                for item1 in item:
                    settings[item1] = item[item1]
                    # print (settings[item1],'vvvvvvvvvvvvvvv')

                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''
                settings['type']='timeline'
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))

            # print(settings2,'gggggggggg')
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def admin_user_activity(partner_id,partner_user,from_data,to_data,category_name,action,associate_to,associate_id,via,extra_info,text_info,title):
        try:
            
            create_date = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            u2 = Admin_activity(partner_id=partner_id,user_id=partner_user,from_data=from_data,to_data=to_data,category_name=category_name,action=action,associate_to=associate_to,associate_id=associate_id,via=via,extra_info=str(extra_info),title=str(title),text_info=text_info,create_date=create_date)
            u2.save()
            output1 = '1'
            return output1
        except Admin_activity.DoesNotExist:
            output = 'No'   

        return output
    
    def admin_timelineSubmit(partner_id,partner_user,data1):
        try:
            # print(data1,"jjjLL")
            data1['user_id'] = partner_user
            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            data1['partner_id'] = partner_id

            u2 = Admin_activity.from_json(json.dumps(data1))
            # print(data1,"jjjLL333")
            u2.save()
            output1 = str(u2.id)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def leadcontactSubmit(lead_id,user_id,data1):
        try:
            data1['create_by'] = user_id
            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            data1['lead_id'] = lead_id
            data1['phone'] = str(data1.get('phone', ''))
            data1['alt_phone'] = str(data1.get('alt_phone', ''))

            u2 = Admin_contacts.from_json(json.dumps(data1))
            u2.save()
            output1 = str(u2.id)
            return output1
        except NotUniqueError as e:
            return '0' 
        
    def get_lead_contact_Details(partner_id,id,partner_user):
        try:
            filter = {}
            # filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            
            pipeline = [      
                            {'$match': match}                           
                        ]
            
            settings = defaultdict(list)

            role = Admin_contacts.objects.aggregate(*pipeline)
            settings6=[]
            
            item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    
            settings2 = json.loads(json_util.dumps(settings))
            
            return settings2
        except NotUniqueError as e:
            return '0'

    def lead_contact_update(lead_id,partner_user,data1,id):
        try:
            
            settings = defaultdict(list)
            settings['modify_date'] = datetime.datetime.utcnow

            data1['phone'] = str(data1.get('phone', ''))
            data1['alt_phone'] = str(data1.get('alt_phone', ''))
            # print(data1)
            for data in data1:

                
                settings[data] = data1[data]
                if data=='_id':
                    del settings[data]
            response = Admin_contacts.objects(lead_id=lead_id,id=ObjectId(id)).update_one(**settings)
            output1 = str(id)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def lead_associate_contactList(lead_id,partner_user,partner_id):
        try:
           
            filter = {}
            filter['lead_id'] = ObjectId(lead_id)
            # filter['company_id'] = ObjectId(company_id)
            
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='_id'
            order=-1
            pipeline = [
                            {"$sort": {sort: order}},
                            {'$match': match},
                        ]
            
            settings = defaultdict(list)

           

            role = Admin_contacts.objects.aggregate(*pipeline)
            settings6=[]
            # print(pipeline)
            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                       
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'

    def delete_lead_contact(id):

        user = Admin_contacts.objects(id=id).first()
        if not user:
            return 'No'
        else:
            user.delete()
            return 'Yes'
        
    def lead_contact_Default(lead_id,id,default=0):
        try:
            data5 = defaultdict(list)
            data5['default'] = 0
            Admin_contacts.objects(lead_id=lead_id).update(**data5)


            data6 = defaultdict(list)
            data6['default'] = 1
            Admin_contacts.objects(id=ObjectId(id)).update_one(**data6)

            # u2.save()
            output1 = id
            return output1
        except NotUniqueError as e:
            return '0'
        
    # def admin_quote_submit(partner_id, user_id, data1):
    #     try:
    #         data1['create_by'] = user_id
    #         data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
    #         data1['partner_id'] = partner_id
            
    #         u2 = Admin_quote.from_json(json.dumps(data1))
    #         u2.save()
    #         # print(contact_name)
    #         output1 = str(u2.id)

    #         return output1
    #     except NotUniqueError as e:
    #         return '0'

    def admin_quote_submit(partner_id, user_id, data1):
        try:
            partner = Partner.objects.get(id=partner_id)
            
            # Use the correct field for the number
            current_number = partner.quote_number
            quote_no = f"{partner.quote_prefix} {current_number}"
            
            # Increment the quote number
            partner.update(set__quote_number=current_number + 1)
            
            # Prepare data1 for saving
            data1['quote_no'] = quote_no
            data1['create_by'] = user_id
            data1['create_date'] = datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            data1['partner_id'] = partner_id
            
            # Save the quote
            u2 = Admin_quote.from_json(json.dumps(data1))
            u2.save()
            
            return str(u2.id)
        except Partner.DoesNotExist:
            return '0'
        except Exception as e:
            print(f"Error: {e}")
            return '0'


        
    def lead_associate_quote(lead_id,partner_user,partner_id):
        try:
           
            filter = {}
            filter['lead_id'] = ObjectId(lead_id)
            # filter['company_id'] = ObjectId(company_id)
            
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='_id'
            order=-1
            pipeline = [
                            {"$sort": {sort: order}},
                            {'$match': match},
                        ]
            
            settings = defaultdict(list)

           

            role = Admin_quote.objects.aggregate(*pipeline)
            settings6=[]
            # print(pipeline)
            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                       
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def get_lead_quote_Details(partner_id,id,partner_user):
        try:
            filter = {}
            # filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            
            pipeline = [      
                            {'$match': match}                           
                        ]
            
            settings = defaultdict(list)

            role = Admin_quote.objects.aggregate(*pipeline)
            settings6=[]
            
            item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1=='lead_id':
                        assigned = item[item1]
                        lead_details = AdminAPI.get_admin_lead_detail(assigned, partner_user, partner_id) 
                        lead_details=Uid.fix_array_lead(lead_details)
                        settings['company_name'] = lead_details.get('company_name','')
                        settings['address'] = lead_details.get('address','')
                        settings['address2'] = lead_details.get('address2','')
                        settings['city'] = lead_details.get('city','')
                        settings['state'] = lead_details.get('state','')
                        settings['pcode'] = lead_details.get('pcode','')
                        settings['country'] = lead_details.get('country','')
                        settings['gstin'] = lead_details.get('gstin','')
                        # settings['company_name'] = lead_details.get('company_name','')

                    elif item1=='plan_id':
                        assigned = item[item1]
                        print(assigned,'kkk')
                        plan_details = AdminAPI.partner_plans_details(assigned, partner_user, partner_id) 
                        plan_details=Uid.fix_array_lead(plan_details)
                        print(plan_details,'kkk')
                        # settings['plan_details'] = plan_details
                        settings['plan_name'] = plan_details.get('plan_name','')
                        settings['brand_name'] = plan_details.get('brand_name','')
                        settings['subject'] = plan_details.get('subject','')
                        settings['price'] = plan_details.get('price','')
                        settings['discount'] = plan_details.get('discount','')
                        settings['tax'] = plan_details.get('tax','')

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    
                        
            settings2 = json.loads(json_util.dumps(settings))
            
            return settings2
        except NotUniqueError as e:
            return '0'

    def lead_quote_update(partner_user,data1,id):
        try:
            
            settings = defaultdict(list)
            settings['modify_date'] = datetime.datetime.utcnow

            # data1['phone'] = str(data1.get('phone', ''))
            # data1['alt_phone'] = str(data1.get('alt_phone', ''))
            # print(data1)
            for data in data1:

                
                settings[data] = data1[data]
                if data=='_id':
                    del settings[data]
            response = Admin_quote.objects(id=ObjectId(id)).update_one(**settings)
            output1 = str(id)
            return output1
        except NotUniqueError as e:
            return '0'
        
    def updateadmincompanyLogo(partner_id,logo):
        try:
            response = Partner.objects(id=partner_id).update_one(logo=logo)
            id = partner_id
        except NotUniqueError as e:
            id = '0'
        return id
    
    def getadminCompanyProfile(partner_id):
        try:
            s = Partner.objects.filter(id=partner_id).to_json()
            organization = json.loads(s)
            organization = Uid.fix_array1(organization)
            output = organization
            
        except Organization.DoesNotExist:
            output = ''   

        return output
    
    # def getproductpricedetails():
    #     try:
    #         s = Admin_product_details.objects.filter().to_json()
    #         organization = json.loads(s)
    #         organization = Uid.fix_array1(organization)
    #         output = organization
            
    #     except Organization.DoesNotExist:
    #         output = ''   

    #     return output
    
    def updatePartner(partner_id,name,phone,email,website,address,address2,city,state,pcode,country,gstin,currency,price,discount,cgst,sgst,product_name,subject):
        try:
            response = Partner.objects(id=partner_id).update_one(name=name,phone=phone,email=email,website=website,address=address,address2=address2,city=city,state=state,pcode=pcode,country=country,gstin=gstin,currency=currency)

            # price_details = Admin_product_details.objects(id=partner_id).upsert_one(
            #     product_name=product_name,
            #     subject=subject, 
            #     price=price,
            #     discount=discount,
            #     cgst=cgst,
            #     sgst=sgst
                
            # )

            id = partner_id
        except NotUniqueError as e:
            id = '0'
        return id
    
    def confirm_Password_new(user_id,password):
        try:
            modify_date = datetime.datetime.utcnow
            user = Partner_user.objects(id=user_id).update_one(password=password)
            output = 'Yes'
        except User.DoesNotExist:
            output = 'No'   

        return output 
        
    def get_partner_org_management(id,partner_user, partner_id):
        try:
           
            filter = {}
            # filter['org_id'] = org_id
            filter['partner_id'] = ObjectId(id)
            
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            
            pipeline = [
                            # {'$lookup': app_config.company_status_lookup},
                            # {'$lookup' : app_config.partner_name},
                            # {'$lookup' : app_config.Plan_type},
                            # {'$lookup': app_config.user_lookup},
                            {'$match': match},
                            
                            # { '$project': app_config.company_project}
                        ]
            
            settings = defaultdict(list)

           

            role = Organization.objects.aggregate(*pipeline)
            settings6=[]
            
            # item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='partner_id':
                        assigned = item[item1]
                        partner_details=AdminAPI.get_partner_details(partner_id, partner_user, partner_id)
                        partner_details=Uid.fix_array3(partner_details)
                        settings['partner_name'] = partner_details.get('name', '')
                    elif item1=='plan_id':
                        assigned = item[item1]
                        plan_details=MongoAPI.getPlansListDetails(assigned)
                        plan_details=Uid.fix_array3(plan_details)
                        settings['plan_name'] = plan_details.get('plan_name', '')
                    elif item1=='org_id':
                        assigned = item[item1]
                        users_list=AdminAPI.UsersNewListGet(assigned, partner_user, partner_id)
                        users_list=Uid.fix_array(users_list)
                        # settings['users_list'] = users_list
                        settings['users_count'] = len(users_list)
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    if item1=='plan_start_date':
                        start_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['start_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        start_date1 = start_date1 + timedelta(hours=offset)


                        plan_start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_start_date'] = plan_start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    if item1=='plan_end_date':
                        end_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        end_date1 = end_date1 + timedelta(hours=offset)


                        plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['plan_end_date'] = plan_end_date
                        settings['end_time'] = end_time
                        settings['date_aging'] = TokenRefresh.calculate_age(end_date2)
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                            settings['mail_signature'] = item2['mail_signature']
                    elif item1=='teams':
                        teams = item[item1]
                        teams= [str(data) for data in teams]
                        settings['teams']=teams                

                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def get_partner_user_management(id,partner_user, partner_id):
        try:
           
            filter = {}
            # filter['status'] = "active"
            filter['partner_id'] = ObjectId(id)
            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            sort='_id'
            order=1
            pipeline = [
                            # {'$lookup': app_config.user1_lookup},
                            # {'$lookup' : app_config.customer_type_lookup},
                            {"$sort": {sort: order}},
                            {'$match': match},
                            
                            # { '$project': app_config.company_project}
                        ]
            
            settings = defaultdict(list)    

            role = Partner_user.objects.aggregate(*pipeline)
            settings6=[]

            item4 = role
            
            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    # if item1 == '_id':
                    #     partner_id = item[item1]

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                        
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=AdminAPI.partnercommontimeset(partner_user,partner_id)

                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date

                    if item1 == 'start_date' or item1 == 'end_date':
                        create_date1 = item[item1]
                        try:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        except ValueError:
                            create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT4).strftime(DATE_FORMAT2)
                        
                        if item1 == 'start_date':
                            settings['start_date'] = create_date
                        elif item1 == 'end_date':
                            settings['end_date'] = create_date
                            settings['create_time'] = create_time

                       
                settings6.append(settings)
                
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
        

    def get_user_permission_Details(id):
        try:
           
            filter = {}
            filter1 = {}
            key = []
            val = []
            # filter['org_id'] = ordId
            filter['_id'] = ObjectId(id)
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            # fields_lookup = {'from': 'product','startWith':'$product_name','connectFromField': 'product','connectToField': '_id','maxDepth':50,'as': 'product_data'}
            pipeline = [
                            # {'$lookup' : app_config.ownerLookup},
                            {'$match'  : match}
                        ]
           
            settings = defaultdict(list)
            # print (pipeline)
            role = Partner_user.objects.aggregate(*pipeline)

            settings6=[]
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                # print (item)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    if item1=='valid_till':
                        valid_till = item[item1]
                        valid_till = datetime.datetime.strptime(str(valid_till), DATE_FORMAT4).strftime(DATE_FORMAT1)
                        settings['valid_till'] = valid_till
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''
                    # if not settings['ticket_view_all']:
                    #     settings['ticket_view_all']=''
            settings2 = json.loads(json_util.dumps(settings))
            print(settings2,'ssssssss')
            return settings2
        except NotUniqueError as e:
            return '0'
        
    def admin_emailSubmit(partner_id,user_id,data1,emailId,attachment):
        try:
            # print(org_id,"222")
            # print(user_id,"ooii")
            # print (data1,"kkt")
            # print (emailId,"///")
            # print(attachment,"mmbb")
            shopping_list = []
            insertData = defaultdict(list)
            
            to_list = data1['to'].split(',')
            print(to_list)
            data2=json.loads(json_util.dumps(data1))
            # print(data2,"99999")
            # if hasattr(data2,'cc'):
            # print('------------------------------------------')
            if data2['cc'] != '':
                cc_list = data2['cc'].split(',')
                data2['cc'] = cc_list
                
            else:
                cc_list = [] 
                data2['cc'] = []
            # else:
            #     cc_list = []
            
            # if hasattr(data2,'bcc'):
            if data2['bcc'] !='':
                bcc_list = data2['bcc'].split(',')
                data2['bcc'] = bcc_list
            else:
                bcc_list = []
                data2['bcc'] = []
            # else:
            #     bcc_list = []
            # print('response',"lllllll")  
            insertData['email_id'] = Uid.generateUUID()
            insertData['partner_id'] = partner_id
            insertData['email_type'] = 'bulk'
            insertData['fromEmail'] = emailId
            insertData['to'] = to_list
            insertData['cc'] = cc_list
            insertData['bcc'] = bcc_list
            insertData['subject'] = data1['subject']
            insertData['content'] = data1['content']
            insertData['attachment'] = attachment.split(",")
            insertData['associate_to'] =  data1['associate_to']
            insertData['associate_id'] =  data1['associate_id']
            insertData['create_by'] =  user_id
            insertData['create_date']=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z')
            # print(insertData,'pppppppppppppp')
            
            u2 = Admin_email.from_json(json.dumps(insertData))
            u2.save()
            response = u2
            
            output1 = str(response.id)
            # print(output1)
            return output1
        except NotUniqueError as e:
            return '0'
        
    
# //////////////////////////////////   ADMIN PANNEL WORK END - NAVEEN   ////////////////////////////////////////////////////////

    def selectLogin(email,password):
       
        try:
            

            s = AdminUser.objects.get(email=email,password=password)
            id1 = json.loads(json_util.dumps(s.admin_user_id))
            id12 = json.loads(json_util.dumps(s))
            id = str(s.id)
            output1 = {'name' : s.name,'email' : s.email,'create_date' : s.create_date,'id':id,'status':s.status}
            output = output1
        except AdminUser.DoesNotExist:
            output = 'User Does Not Exists'        
        return output

    def emailCheck(email):
        try:
            s = AdminUser.objects.get(email=email)
            output = 'Yes'
        except AdminUser.DoesNotExist:
            output = 'No'   

        return output
    
    def emailCheckNew(email):
        try:
            s = AdminUser.objects.get(email=email,approved='1')
            output = 'Yes'
        except AdminUser.DoesNotExist:
            output = 'No'   

        return output

    def createUser(email,password,name):
        try:
            data1 = defaultdict(list)
            data1['email'] = email
            data1['password'] = password
            data1['name'] = name
            user = AdminUser(**data1)
            response = user.save()
            output1 = {'user_id' : str(response.id)}
            return output1
        except NotUniqueError as e:
            return ''

    def getOrganizationList(ordId,length,page,search_string,date_from,date_to,order,sort):  
        try: 
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            if date_from:
                y = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%d')
                search_time=datetime.datetime(int(y),int(m),int(d),0,0)
            if date_to:
                y = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%d')
                nextday=datetime.datetime(int(y),int(m),int(d),23,59)
                filter['create_date'] = {"$gte": search_time,"$lte": nextday}
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            {'$match':{
                                '$or': [
                                {'organization_name': { "$regex": search_string, "$options" :'i'}}, 
                                {'phone': { "$regex": search_string, "$options" :'i'}}, 
                                {'email': { "$regex": search_string, "$options" :'i'}}, 
                                ],
                            
                            }},
                            {'$skip'   : sData1},
                            {'$limit'  : length},
                            {'$project': app_config.organization_project}
                        ]
            
            settings = defaultdict(list)
            role = Organization.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    elif item1=='_id':
                        assigned = item[item1]
                    elif item1=='org_id':
                        assigned = item[item1]
                        settings['no_of_users']=AdminAPI.getOrgUserCount(item[item1])
                    elif item1=='modify_date':
                        modify_date1 = item[item1]
                        modify_date = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        modify_time = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = modify_date
                        settings['modify_time'] = modify_time
                        settings['last_modified'] = TokenRefresh.calculate_age(modify_date)

                    elif item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        # settings['date_aging'] = TokenRefresh.calculate_age(create_date2)

                    elif item1=='start_date':
                        start_date1 = item[item1]
                        start_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        start_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['start_date'] = start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    
                    elif item1=='end_date':
                        end_date1 = item[item1]
                        print(end_date1)
                        # end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        # end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        settings['end_date'] = end_date2
                        # settings['end_time'] = end_time
                        settings['remaining_days'] = TokenRefresh.calculate_age(end_date2)

              
                    else:
                        data = {item1:item4}
                   
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
    
    def getOrgCountData():
        try:
            org_total = Organization.objects().count()
            return org_total
        except NotUniqueError as e:
            return '0'

    def getOrgUserCount(org_id):
        try:
            users_count = User.objects(org_id=org_id).count()
            return users_count
        except NotUniqueError as e:
            return '0'

    def getOrgDetails(id):
        try:
            
            filter = {}
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$lookup': app_config.countriesLookup},
                            {'$lookup': app_config.statesLookup},
                            {'$match': match},
                            {'$project': app_config.organization_project}
                       ]
            
            settings = defaultdict(list)
            role = Organization.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='org_id':
                        assigned = item[item1]
                        # admin_user = AdminAPI.getOrgUser(item[item1],item['email'])
                        admin_user=''
                        settings['admin_user']=admin_user
                        settings['no_of_users']=AdminAPI.getOrgUserCount(item[item1])
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    elif item1=='customerType':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['customer_type_name'] = item2['name']
                    if item1=='modify_date':
                        modify_date1 = item[item1]
                        modify_date = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        modify_time = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = modify_date
                        settings['modify_time'] = modify_time
                        settings['last_modified'] = TokenRefresh.calculate_age(modify_date)

                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    elif item1=='start_date':
                        start_date1 = item[item1]
                        # print(start_date1)
                        start_date = datetime.datetime.strptime(str(start_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        start_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['start_date'] = start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    elif item1=='end_date':
                        end_date1 = item[item1]
                        end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        settings['end_date'] = end_date
                        settings['remaining_days'] = TokenRefresh.calculate_remaining(end_date)

                  #work
                    
                    # elif item1=='end_date':
                    #     end_date1 = item[item1]
                    #     end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                    #     end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                    #     end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                    #     settings['end_date'] = end_date
                    #     settings['end_time'] = end_time
                    #     settings['remaining_days'] = TokenRefresh.calculate_remaining(end_date2)
                    # elif item1=='end_date':
                    #     end_date1 = item[item1]
                    #     end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                    #     end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                    #     end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                    #     settings['end_date'] = end_date
                    #     settings['end_time'] = end_time
                    #     settings['remaining_days'] = TokenRefresh.calculate_remaining(end_date2)
                    else:
                        data = {item1:item4}
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return '0'

    def getOrgUser(org_id,email):
        try:
            filter = {}
            filter['org_id'] = int(org_id)
            filter['email'] = email
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$match': match},
                            {'$project': app_config.user_project}
                       ]
            settings = defaultdict(list)
            role = User.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return '0'

    def getOrganizationUserList(ordId,length,page,search_string,owner,source,customer_type,date_from,date_to,order,sort,current_user):

        try: 
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            if date_from:
                y = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%d')
                search_time=datetime.datetime(int(y),int(m),int(d),0,0)
            if date_to:
                y = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%d')
                nextday=datetime.datetime(int(y),int(m),int(d),23,59)
                filter['create_date'] = {"$gte": search_time,"$lte": nextday}
            filter['org_id'] = int(ordId)
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$lookup' : app_config.role_lookup},
                            {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            {'$match':{
                                '$or': [
                                {'name': { "$regex": search_string, "$options" :'i'}}, 
                                {'phone': { "$regex": search_string, "$options" :'i'}}, 
                                {'email': { "$regex": search_string, "$options" :'i'}}, 
                                ],
                            
                            }},
                            {'$skip'   : sData1},
                            {'$limit'  : length},
                            {'$project': app_config.user_project}
                        ]
            
            settings = defaultdict(list)
            role = User.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='roleData':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['role_name'] = item2['role_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    elif item1=='_id':
                        assigned = item[item1]
                    elif item1=='org_id':
                        assigned = item[item1]
                        settings['no_of_users']=AdminAPI.getOrgUserCount(item[item1])
                    elif item1=='modify_date':
                        modify_date1 = item[item1]
                        modify_date = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        modify_time = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = modify_date
                        settings['modify_time'] = modify_time
                        settings['last_modified'] = TokenRefresh.calculate_age(modify_date)

                    elif item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    else:
                        data = {item1:item4}
                   
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
    
    def getOrgUserCountData(org_id):
        try:
            org_total = User.objects(org_id=int(org_id)).count()
            return org_total
        except NotUniqueError as e:
            return '0'

    def changeCrmUserStatus(id,status):
        try:
            response = User.objects(id=ObjectId(id)).update_one(status=status)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id

    def changeCrmUserPassword(id,password):
        try:
            response = User.objects(id=ObjectId(id)).update_one(password=password)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id

    def changeOrgStatus(org_id,status):
        try:
            response = Organization.objects(org_id=int(org_id)).update_one(status=status)
            user_update =User.objects(org_id=org_id).update(status=status)
            id = org_id
        except NotUniqueError as e:
            id = '0'
        return id
    def getAdminUserDetails(id):

        try:
            filter = {}
            filter['_id'] = ObjectId(id)
            key = []
            val = []
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$match': match}
                        ]
            settings = defaultdict(list)
            # print (pipeline)
            role = AdminUser.objects.aggregate(*pipeline)
            settings6=[]
            item4 = role
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    if item1=='role':
                        assigned = item[item1]
                        settings['role']=str(assigned)
                     
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    else:
                        data = {item1:item4}            
            settings2 = json.loads(json_util.dumps(settings))
            return settings2
        except NotUniqueError as e:
            return 'No'

    def liveUsersList(ordId,length,page,search_string,status,sort,order):
        try:
            print(search_string)
            print('ooooooooooooooo')
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            # filter['org_id'] = ordId
            # if search :
            #     filter1['name__contains'] = search
            #     filter['name__contains'] = search

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            pipeline = [
                            {'$lookup' : app_config.org_lookup},
                            {'$lookup' : app_config.user_audit_lookup},
                            # {'$graphLookup' : fields_lookup},
                            {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            # {'$match':{
                            #     '$or': [
                            #     {'org_name': { "$regex": search_string, "$options" :'i'}}, 
                            #     {'user_name': { "$regex": search_string, "$options" :'i'}}, 
                            #     ],
                            # }},
                            {'$skip'   : sData1},
                            {'$limit'  : length},
                            {'$project': app_config.user_audit_project}
                        ]
            settings = defaultdict(list)

            role = User_audit.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    if item1=='start_time':
                        start_time1 = item[item1]
                        start_date = datetime.datetime.strptime(str(start_time1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(start_time1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['start_date'] = start_date
                        settings['start_time'] = start_time
                        st_time = datetime.datetime.strptime(start_time, "%H:%M %p")
                        st_time1=st_time.strftime("%r")
                        settings['start_time'] = st_time1

                    if item1=='end_time':
                        end_time1 = item[item1]
                        end_date = datetime.datetime.strptime(str(end_time1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_time1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['end_date'] = end_date
                        settings['end_time'] = end_time
                        et_time = datetime.datetime.strptime(end_time, "%H:%M %p")
                        et_time1=et_time.strftime("%r")
                        settings['end_time'] = et_time1
                        diff = et_time - st_time
                        hours = int(diff.seconds // (60 * 60))
                        settings['duration'] = hours
                    # if item1=='org_detail':
                    #     user_create_date1 = item[item1][0]['create_date']
                    #     user_create_date = datetime.datetime.strptime(str(user_create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                    #     user_create_time = datetime.datetime.strptime(str(user_create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                    #     settings['user_create_date'] = user_create_date
                    #     settings['user_create_time'] = user_create_time

                    if item1=='org_detail':
                        organization_name = item[item1][0]['organization_name']
                        settings['org_name'] = organization_name
                        create_date = item[item1][0]['create_date']
                        create_date = datetime.datetime.strptime(str(create_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        settings['org_create_date'] = create_date

                        if 'start_date' in item[item1][0]:
                            start_date = item[item1][0]['start_date']
                            # print(start_date)
                            start_date = datetime.datetime.strptime(str(start_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                            settings['org_start_date'] = start_date
                        else:
                            settings['org_start_date'] = ''

                        if 'end_date' in item[item1][0]:
                            end_date = item[item1][0]['end_date']
                            end_date = datetime.datetime.strptime(str(end_date), DATE_FORMAT3).strftime(DATE_FORMAT1)
                            settings['org_end_date'] = end_date
                            settings['remaining_days'] = TokenRefresh.calculate_remaining(end_date)
                        else:
                            settings['org_end_date'] = ''

                    if item1=='user_detail':
                        user_name = item[item1][0]['name']
                        settings['user_name'] = user_name
                        user_email = item[item1][0]['email']
                        settings['user_email'] = user_email

                    if item1=='target_date':
                        target_date = item[item1]
                        target_date = datetime.datetime.strptime(str(target_date), DATE_FORMAT4).strftime(DATE_FORMAT1)
                        settings['target_date'] = target_date
                    else:
                        data = {item1:item4}
                  

                settings6.append(settings)
            
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'

    def liveUsersListCount(org_id,status):
        try:
            user_total = User_audit.objects().count()
            return user_total
        except NotUniqueError as e:
            return '0'

    def getAdminUserList(ordId,length,page,search,sort,order):
        try:
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
    
            # if search :
            #     filter1['name__contains'] = search
                # filter['name__contains'] = search
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [
                            {'$lookup' : app_config.report_to_lookup},
                            {'$lookup' : app_config.role_lookup},
                            # {'$graphLookup' : fields_lookup},
                            {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            {'$match':{
                                '$or': [
                                {'name': { "$regex": search, "$options" :'i'}}, 
                                {'email': { "$regex": search, "$options" :'i'}},
                                ],
                            }},
                            {'$skip'   : sData1},
                            {'$limit'  : length},
                            {'$project': app_config.user_project}
                        ]
            
            settings = defaultdict(list)

            role = AdminUser.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='currency':
                        settings[item1] = item[item1]
                    elif item1=='report':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    
                    if item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
             

                    if item1=='target_date':
                        target_date = item[item1]
                        target_date = datetime.datetime.strptime(str(target_date), DATE_FORMAT4).strftime(DATE_FORMAT1)
                        settings['target_date'] = target_date
                    else:
                        data = {item1:item4}
                    if not settings['report']:
                        settings['report']=''
                    if not settings['roleData']:
                        settings['roleData']=''
                    

                settings6.append(settings)
            
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'

    def getAdminUserListCount():
        try:
            user_total = AdminUser.objects().count()
            return user_total
        except NotUniqueError as e:
            return '0'

    def userCheck(email):
        try:
            s = AdminUser.objects.get(email=email)
            if s.email:
                output = 'Yes'
            else:
                output = 'No'
                
        except AdminUser.DoesNotExist:
            output = 'No'   

        return output

    # def userCheckNew(email):
    #     try:
    #         s = AdminUser.objects.get(email=email,approved=1)
    #         if s.email:
    #             output = 'Yes'
    #         else:
    #             output = 'No'
                
    #     except AdminUser.DoesNotExist:
    #         output = 'No'   

    #     return output

    def createUser(email,password,name):

        try:
            data1 = defaultdict(list)
            data1['email'] = email
            data1['password'] = password
            data1['name'] = name
            user = AdminUser(**data1)
            response = user.save()
            output1 = {'user_id' : str(response.id)}
            return output1
        except NotUniqueError as e:
            return ''

    def createAdminUser(email,password,name,phone):

        try:
            user = AdminUser(email=email,name=name,password=password,phone=phone)
            response = user.save()
            output1 = {'user_id' : response.id}
            return output1
        except NotUniqueError as e:
            return ''

    def changeAdminUserStatus(id,status):
        try:
            response = AdminUser.objects(id=ObjectId(id)).update_one(status=status)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id

    def changeAdminUserPassword(id,password):
        try:
            response = AdminUser.objects(id=ObjectId(id)).update_one(password=password)
            id = id
        except NotUniqueError as e:
            id = '0'
        return id

    def adminUserUpdate(email,name,phone,id):
        try:
            modify_date = datetime.datetime.utcnow
            user_id = id
            user = AdminUser.objects(id=id).update_one(email=email,name=name,phone=phone)
            output = 'Yes'
        except User.DoesNotExist:
            output = 'No'   
        return output

    def getTicketList(ordId,length,page,search_string,owner,source,customer_type,date_from,date_to,order,sort,current_user):
        try: 
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            if date_from:
                y = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%d')
                search_time=datetime.datetime(int(y),int(m),int(d),0,0)
            if date_to:
                y = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%d')
                nextday=datetime.datetime(int(y),int(m),int(d),23,59)
                filter['create_date'] = {"$gte": search_time,"$lte": nextday}
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [    {'$lookup' : app_config.org_lookup},
                            {'$lookup' : app_config.user_audit_lookup},
                            {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            {'$skip'   : sData1},
                            {'$limit'  : length},
                            {'$project': app_config.ticket_project}
                        ]
            
            settings = defaultdict(list)
            role = SupportTicket.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    elif item1=='_id':
                        assigned = item[item1]
                    elif item1=='org_id':
                        assigned = item[item1]
                        settings['no_of_users']=AdminAPI.getOrgUserCount(item[item1])
                    elif item1=='modify_date':
                        modify_date1 = item[item1]
                        modify_date = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        modify_time = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = modify_date
                        settings['modify_time'] = modify_time
                        settings['last_modified'] = TokenRefresh.calculate_age(modify_date)

                    elif item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        # settings['date_aging'] = TokenRefresh.calculate_age(create_date2)

                    elif item1=='start_date':
                        start_date1 = item[item1]
                        start_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        start_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['start_date'] = start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    
                    elif item1=='end_date':
                        end_date1 = item[item1]
                        end_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        end_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['end_date'] = start_date
                        settings['end_time'] = start_time
                        settings['remaining_days'] = TokenRefresh.calculate_age(end_date2)

              
                    else:
                        data = {item1:item4}
                   
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
    
    def getTicketCountData():
        try:
            ticket_total = SupportTicket.objects().count()
            return ticket_total
        except NotUniqueError as e:
            return '0'

    def getEnquiryList(ordId,length,page,search_string,date_from,date_to,order,sort):
        try: 
            sData = int(page)*int(length)
            length1 = int(page)-1
            sData1 = int(length)*int(length1) 
            filter = {}
            filter1 = {}
            key = []
            val = []
            if date_from:
                y = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_from, "%d/%m/%Y").strftime('%d')
                search_time=datetime.datetime(int(y),int(m),int(d),0,0)
            if date_to:
                y = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%Y')
                m = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%m')
                d = datetime.datetime.strptime(date_to, "%d/%m/%Y").strftime('%d')
                nextday=datetime.datetime(int(y),int(m),int(d),23,59)
                filter['create_date'] = {"$gte": search_time,"$lte": nextday}
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [  
                            {'$sort'   : {sort : order}},
                            {'$match'  : match},
                            {'$skip'   : sData1},
                            {'$limit'  : length},
                            {'$project': app_config.enquiry_project}
                        ]
            
            settings = defaultdict(list)
            role = Enquiry.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='assigned':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1=='account':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['company_name'] = item2['company_name']
                    elif item1=='countryId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['country_id'] = item2['id']
                    elif item1=='stateId':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['state_id'] = item2['id']
                    elif item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                    elif item1=='_id':
                        assigned = item[item1]
                    elif item1=='org_id':
                        assigned = item[item1]
                        settings['no_of_users']=AdminAPI.getOrgUserCount(item[item1])
                    elif item1=='modify_date':
                        modify_date1 = item[item1]
                        modify_date = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        modify_time = datetime.datetime.strptime(str(modify_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = modify_date
                        settings['modify_time'] = modify_time
                        settings['last_modified'] = TokenRefresh.calculate_age(modify_date)

                    elif item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        # settings['date_aging'] = TokenRefresh.calculate_age(create_date2)

                    elif item1=='start_date':
                        start_date1 = item[item1]
                        start_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        start_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        start_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['start_date'] = start_date
                        settings['start_time'] = start_time
                        settings['date_aging'] = TokenRefresh.calculate_age(start_date2)
                    
                    elif item1=='end_date':
                        end_date1 = item[item1]
                        end_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT_mdy)
                        end_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['end_date'] = start_date
                        settings['end_time'] = start_time
                        settings['remaining_days'] = TokenRefresh.calculate_age(end_date2)

              
                    else:
                        data = {item1:item4}
                   
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'
    
    def getEnquiryCountData():
        try:
            ticket_total = Enquiry.objects().count()
            return ticket_total
        except NotUniqueError as e:
            return '0'

    def getSignupCount(from_date,to_date):
        try:

            filter = {}
            filter['create_date'] = {"$gte": from_date,"$lte": to_date}
            match = filter
            pipeline = [
                            {'$project': app_config.organization_project},
                            {'$match': match},

                       ]
            data = Organization.objects.aggregate(*pipeline)
            count_array=json.loads(json_util.dumps(data))
            if len(count_array) == 0:
                count = 0
            else:
                count =len(count_array)
            return count
        except NotUniqueError as e:
            return '0'

    def getOrgCount(status):
        try:
            total = Organization.objects(status=status).count()
            return total
        except NotUniqueError as e:
            return '0'
    # def getUserCount(status):
    #     try:
    #         total = AdminUser.objects(status=status).count()
    #         return total
    #     except NotUniqueError as e:
    #         return '0'
    def getUserCount(status):
        try:
            total = User.objects(status=status).count()
            return total
        except NotUniqueError as e:
            return '0'

    def deleteData(org_id):
        try:
            obj1 = Contact.objects(org_id=org_id)
            obj1.delete()
            # obj2 = Account.objects(org_id=org_id)
            # obj2.delete()
            # obj3 = Deal.objects(org_id=org_id)
            # obj3.delete()
            # obj4 = Quote.objects(org_id=org_id)
            # obj4.delete()
            # obj5 = Proforma.objects(org_id=org_id)
            # obj5.delete()
            # obj6 = Invoice.objects(org_id=org_id)
            # obj6.delete()
            # obj7 = Follow_up.objects(org_id=org_id)
            # obj7.delete()
            # obj8 = Email.objects(org_id=org_id)
            # obj8.delete()
            # obj9 = Document.objects(org_id=org_id)
            # obj9.delete()
            # obj10 = Organization.objects(org_id=org_id)
            # obj10.delete()
            # obj11 = Role.objects(org_id=org_id)
            # obj11.delete()
            # obj12 = PdfSettings.objects(org_id=org_id)
            # obj12.delete()
            # obj13 = Numbering.objects(org_id=org_id)
            # obj13.delete()
            # obj13 = Activity.objects(org_id=org_id)
            # obj13.delete()
            # obj14 = Accounttmp.objects(org_id=org_id)
            # obj14.delete()
            # obj15 = Contacttmp.objects(org_id=org_id)
            # obj15.delete()
            # obj16 = Producttemp.objects(org_id=org_id)
            # obj16.delete()
            # obj17 = Rename.objects(org_id=org_id)
            # obj17.delete()
            # obj18 = SalesProcess.objects(org_id=org_id)
            # obj18.delete()
            # obj19 = SalesSubProcess.objects(org_id=org_id)
            # obj19.delete()
            # obj20 = DealsCheckList.objects(org_id=org_id)
            # obj20.delete()
            # obj21 = DealsSubCheckList.objects(org_id=org_id)
            # obj21.delete()
            # obj22 = SalesProcessTemplate.objects(org_id=org_id)
            # obj22.delete()
            # obj23 = DealsStageMapping.objects(org_id=org_id)
            # obj23.delete()
            # obj24 = Fields.objects(org_id=org_id)
            # obj24.delete()
            # obj25 = Note.objects(org_id=org_id)
            # obj25.delete()
            # obj26 = Numbering.objects(org_id=org_id)
            # obj26.delete()
            # obj27 = Product.objects(org_id=org_id)
            # obj27.delete()
            # obj28 = SupportTicket.objects(org_id=org_id)
            # obj28.delete()
            # obj29 = User.objects(org_id=org_id)
            # obj29.delete()
            # obj30 = User_audit.objects(org_id=org_id)
            # obj30.delete()
            # obj31 = Email_template.objects(org_id=org_id)
            # obj31.delete()
            return '1'
        except NotUniqueError as e:
            return '0'

    def addNewAddon(addon,addon_name,description):
        try:
            addon = AddOn(addon=addon,addon_name=addon_name,description=description)
            response = addon.save()
            output1 = {'addon_id' : response.id}
            return output1
        except NotUniqueError as e:
            return ''
    def mapAddon(org_id,addon,addon_id,status):
        try:
            check_addon= AdminAPI.addonCheck(org_id,addon_id)
            if check_addon=='Yes':
                addon = OrgAddon.objects(org_id=org_id,addon_id=ObjectId(addon_id)).update_one(status=status)
                output1 ='1'
            else:
                addon = OrgAddon(org_id=org_id,addon=addon,addon_id=ObjectId(addon_id),status=status)
                response = addon.save()
                output1 = {'addon_id' : response.id}
            return output1
        except NotUniqueError as e:
            return ''

    def addonCheck(org_id,addon_id):
        try:
            s = OrgAddon.objects.get(org_id=org_id,addon_id=ObjectId(addon_id))
            output = 'Yes'
        except OrgAddon.DoesNotExist:
            output = 'No'   

        return output

    def alladdonList():
        try:
            s = AddOn.objects.filter().to_json()
            output = json.loads(s)
        except AddOn.DoesNotExist:
            output = 'No'   
        return output

    def getOrgAddon(org_id):
        try:
            s = OrgAddon.objects.filter(org_id=org_id).to_json()
            output = json.loads(s)
        except OrgAddon.DoesNotExist:
            output = 'No'   
        return output
    

