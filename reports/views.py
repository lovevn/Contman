from django.http import HttpResponse
from django.db.models import Count
from django.db import connections
from django.shortcuts import get_object_or_404,render_to_response,render
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from content.models import SMS,Dynpath
from django.http import HttpResponse
from contman.settings import LOG_FILE
from datetime import datetime,date
from reports.forms import SearchForm
import pdb
# Create your views here.

@login_required(login_url='/admin/login/')
def show_log(request):
	log_data = tail(LOG_FILE)

	return render_to_response('log_report.html', {'log_entries':log_data}) 

def tail(file_name,window=20):
	f = open(file_name)
	BUFSIZE = 1024
	f.seek(0, 2)
	bytes = f.tell()
	size = window
	block = -1
	data = []
	while size > 0 and bytes > 0:
		if (bytes - BUFSIZE > 0):
			f.seek(block*BUFSIZE, 2)
			data.append(f.read(BUFSIZE))
		else:
			f.seek(0,0)
			data.append(f.read(bytes))
		linesFound = data[-1].count('\n')
		size -= linesFound
		bytes -= BUFSIZE
		block -= 1

        log_lines = ''.join(data).splitlines()[-window-1:]
        if log_lines[-1][-1] == "\n":
            return log_lines
        return log_lines[:-1]


def to_georgian(datestring):
    '''converts a date string into a georgian integer'''
    georgian = datetime.strptime(datestring,'%Y-%m-%d').date().toordinal()
    return georgian

def to_month_number(datestring):
    '''converts a date string into a month integer'''
    if ' ' in datestring:
        datestring = datestring.split()[0]
    month = datetime.strptime(datestring,'%Y-%m-%d').date().month
    return month

def extract_week_no(ds):
        d = datetime.strptime(ds,'%Y-%m-%d').isocalendar()[1]
        return d

def next_month(last_result):
    last_date = datetime.strptime(last_result,'%Y-%m-%d').date()
    m = last_date.month
    y = last_date.year
    m += 1
    if m == 13:
        m = 1
        y += 1
    first_of_next_month = date(y, m, 1)
    return first_of_next_month.strftime('%Y-%m-%d')

def next_day(current_day):
    return date.fromordinal(to_georgian(current_day) + 1).strftime('%Y-%m-%d')

def fill_gaps(results,qtype,start_d,end_d):
    '''adds entries to list with 0es for dates where not data was found'''
    to_date_integer={'by_day':to_georgian,'by_month':to_month_number}
    next_date={'by_day':next_day,'by_month':next_month} 
    stored_results = list(results)
    end_date = datetime.strptime(end_d,'%Y-%m-%d').date()
    start_date = datetime.strptime(start_d,'%Y-%m-%d').date()     

    #make sure all dates displayed for month report start at first day of month.
    if qtype == 'by_month':
        end_d = date(end_date.year, end_date.month, 1).strftime('%Y-%m-%d')

    #add start date and end date to list if not in results already, to make sure it is filled with 0s
    end_date_found = False
    start_date_found = False
    for result in stored_results:
        if end_d in result['date_created']:
            end_date_found = True
        if start_d in result['date_created']:
            start_date_found = True
    if not end_date_found:
        stored_results.append({'date_created': end_d, 'created_count': 0})
    if not start_date_found:
        stored_results.insert(0,{'date_created': start_d, 'created_count': 0})

    no_gap_results = []
    last_result = lambda:no_gap_results[-1]['date_created']
    for entry in stored_results:
        date_delta = lambda:to_date_integer[qtype](entry['date_created']) - to_date_integer[qtype](last_result())
        if len(no_gap_results) == 0:
            no_gap_results.append(entry)
            continue
        else:
            #if consecutive
            if date_delta() == 1:
                no_gap_results.append(entry)
            #if same date
            elif date_delta() == 0:
                no_gap_results.append(entry)
                continue
            else:
                #while not consecutive
                while (date_delta() != 1):
                    next_d = next_date[qtype](last_result())
                    next_empty_entry = {'date_created': next_d, 'created_count': 0}
                    no_gap_results.append(next_empty_entry)
                no_gap_results.append(entry)
                continue
    return no_gap_results


def report_by_date(start_d,end_d):
    '''Fetches the results from a specific set of dates, and groups
    results by day, also filling the gaps in and days with no results'''
    start_date = start_d.strftime('%Y-%m-%d')
    end_date = end_d.strftime('%Y-%m-%d')
    query_results = SMS.objects.filter(
                    received__range=[start_d,end_d]
                    ).extra(
                        {'date_created' : "date(received)"}
                    ).values(
                        'date_created'
                    ).annotate(created_count=Count('id'))
    return fill_gaps(query_results,'by_day',start_date, end_date)


def remove_time(datelist):
    '''Removes time information for each datetime string in list "datelist" returning
    a new list with only dates'''
    clean_results = []
    for entry in datelist:
        if ' ' in entry['date_created']:
            only_date = entry['date_created'].split()[0]
            clean_results.append({'date_created':only_date,'created_count':entry['created_count']})
        else:
            clean_results.append(entry)
    return clean_results


def report_by_month(start_d,end_d):
    start_date = start_d.strftime('%Y-%m-%d')
    end_date = end_d.strftime('%Y-%m-%d')

    query_results = SMS.objects.filter(
                    received__range=[start_date,end_date]
                    ).extra(
                        select={'date_created': connections[SMS.objects.db].ops.date_trunc_sql('month', 'received')}
                    ).values('date_created'
                    ).annotate(
                        created_count=Count('received')
                    )
    results = remove_time(query_results)
    return fill_gaps(results,'by_month',start_date, end_date)


@login_required(login_url='/admin/login/')
def search(request):
    if request.method == 'POST':
        form = SearchForm(request.POST)
        if form.is_valid():
            detailed_results = report_by_date(form.cleaned_data['sdate'],form.cleaned_data['edate'])
            summary = report_by_category(form.cleaned_data['sdate'],form.cleaned_data['edate'])
            return render(request,'sms_report.html', { 'form': form,'results': detailed_results, 'summary': summary })
    else:
        form = SearchForm()
    return render(request,'sms_report.html', {'form': form})

def report_by_category(start_d,end_d):
    """Returns a list of quantity of content requested in given time range
    grouped by category"""
    start_date = start_d.strftime('%Y-%m-%d')
    end_date = end_d.strftime('%Y-%m-%d')
    
    query_results = Dynpath.objects.filter(
                    created__range=[start_date,end_date]
                    ).values('payload__content_type__name'
                    ).annotate(hits=Count("payload")
                    )
    return query_results


