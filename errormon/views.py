import datetime
import time
import logging
from django.contrib.auth.decorators import user_passes_test

from google.appengine.api import taskqueue

from django.template.context import RequestContext
from django.shortcuts import render, render_to_response
from django.http import HttpResponse, HttpRequest
from django.utils import simplejson

from errormon.models import ExceptionModel

def admin_required(function=None):
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated() and u.is_superuser,
    )
    if function:
        return actual_decorator(function)
    return actual_decorator

@admin_required()
def home(request):
    """Show list of recent errors."""
    num_errors = 20
    recent_errors = list(ExceptionModel.objects.all().order_by("-occurred_at")[:num_errors])
    ctx = {
        "num_errors" : num_errors,
        "recent_errors": recent_errors,
    }
    return render_to_response('errormon/home.html',
            ctx, context_instance=RequestContext(request))

@admin_required()
def status(request):
    """Return 500 if errors occurred in last few minutes, 200 otherwise."""
    num_mins = request.GET.get("window", 5)
    fmt = request.GET.get("fmt", "html")
    if not fmt in ["json", "html"]:
        fmt = "html"
    mins_ago = datetime.datetime.now() - datetime.timedelta(minutes=num_mins)
    recent_errors = list(ExceptionModel.objects.filter(occurred_at__gte=mins_ago).order_by("-occurred_at"))
    has_errors = len(recent_errors) > 0
    status_code = has_errors and 500 or 200
    ctx = {
        "has_errors" : has_errors,
        "num_errors" : len(recent_errors),
        "recent_errors" : recent_errors,
        "num_mins" : num_mins,
        "status_code": status_code,
    }
    if fmt == "html":
        response = render(request, 'errormon/status.html',
                ctx, context_instance=RequestContext(request))
        response.status_code = status_code
    else:
        ctx["recent_errors"] = list([repr(x) for x in recent_errors])
        response = HttpResponse(simplejson.dumps(ctx), mimetype="application/json")
        response["Access-Control-Allow-Origin"] = "*"
    return response

def status_summary(request):
    """Return number of recent errors as json."""
    num_mins = max(1, min(100, request.GET.get("window", 5)))
    fmt = request.GET.get("fmt", "html")
    if not fmt in ["json", "html"]:
        fmt = "html"
    mins_ago = datetime.datetime.now() - datetime.timedelta(minutes=num_mins)
    num_errors = ExceptionModel.objects.filter(occurred_at__gte=mins_ago).order_by("-occurred_at").count()
    has_errors = num_errors > 0
    status_code = has_errors and 500 or 200
    ctx = {
        "has_errors" : has_errors,
        "num_errors" : num_errors,
        "num_mins" : num_mins,
        "status_code": status_code,
    }
    if fmt == "html":
        response = render(request, 'errormon/status_summary.html',
                ctx, context_instance=RequestContext(request))
        response.status_code = status_code
    else:
        response = HttpResponse(simplejson.dumps(ctx), mimetype="application/json")
        response["Access-Control-Allow-Origin"] = "*"
    return response

def delete_old(request):
    """Deletes errors that are more than a week old."""

    num_tasks = int(request.GET.get("num_tasks", 0))
    deleted = int(request.GET.get("deleted", 0))
    initial_deleted = deleted
    num_days = request.GET.get("window", 7)
    days_ago = datetime.datetime.now() - datetime.timedelta(days=num_days)
    batch_size = 20

    start = time.time()

    done = False
    if num_tasks < 100:
        while True:
            old_errors = list(ExceptionModel.objects.filter(occurred_at__lte=days_ago)[:batch_size])
            batch_deleted = 0
            for old_error in old_errors:
                old_error.delete()
                batch_deleted += 1
                deleted += 1
                time_taken = time.time() - start
                if time_taken > 10:
                    break
            less_found_than_batch_size = len(old_errors) < batch_size
            deleted_all_found = len(old_errors) == batch_deleted
            if less_found_than_batch_size and deleted_all_found:
                done = True
                break

            time_taken = time.time() - start
            if int(time_taken) > 10:
                if not done:
                    taskqueue.add(url="/errormon/delete_old/", method='GET',
                                params={"num_tasks": num_tasks + 1, "deleted": deleted})
                break
    else:
        logging.warn("Took more than 100 tasks to delete old errors!")

    time_taken = time.time() - start
    return HttpResponse("Deleted %s old errors in %s seconds (task: %d, done: %s)" % (
                deleted - initial_deleted, time_taken, num_tasks, done),
            mimetype="text/plain", status=200)

@admin_required()
def sample_error(request):
    raise Exception("example error")