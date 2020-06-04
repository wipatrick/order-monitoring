from flask import request
from flask import make_response
from flask import Flask
from messages_pb2 import OrderState, OrderUpdate, OrderStatus, Report, Time

from statefun import StatefulFunctions
from statefun import RequestReplyHandler
from statefun import kafka_egress_record

from datetime import datetime
import time

functions = StatefulFunctions()

@functions.bind("lieferbot/monitoring")
def monitore(context, order_update: OrderUpdate):
    # Stateful function, represents the orders
    state = context.state('order_state').unpack(OrderState)
    if not state:
        state = OrderState()
        state.status = 0
    else:
        state.status += 1
    context.state('order_state').pack(state)

    if state.status == 0:
        timeunassigned = context.state('time_unassigned').unpack(Time)
        if not timeunassigned:
            t = time.time()
            timeunassigned = Time()
            timeunassigned.time = t
        context.state('time_unassigned').pack(timeunassigned)
    elif state.status == 1:
        timeassigned = context.state('time_assigned').unpack(Time)
        t = time.time()
        timeassigned = Time()
        timeassigned.time = t
        context.state('time_assigned').pack(timeassigned)

    elif state.status == 2:
        timeprogress = context.state('time_in_progress').unpack(Time)
        if not timeprogress:
            t = time.time()
            timeprogress = Time()
            timeprogress.time = t
        context.state('time_in_progress').pack(timeprogress)

    elif state.status == 3:
        timedelivered = context.state('time_delivered').unpack(Time)
        if not timedelivered:
            t = time.time()
            timedelivered = Time()
            timedelivered.time = t
        context.state('time_delivered').pack(timedelivered)

        report = compute_report(context, order_update, state.status)

        egress_message = kafka_egress_record(
            topic="reports",  key=order_update.id, value=report)
        context.pack_and_send_egress("lieferbot/status", egress_message)

    response = compute_status(order_update, state.status)

    egress_message = kafka_egress_record(
        topic="status", key=order_update.id, value=response)
    context.pack_and_send_egress("lieferbot/status", egress_message)

    
def compute_report(context, order_update: OrderUpdate, state):
    # Compute the final report, after an order has reached the state delivered
    report = Report()
    report.id = order_update.id
    report.vehicle = order_update.vehicle

    timeunassigned = context.state('time_unassigned').unpack(Time)
    report.timeUnassigned = timeunassigned.time
    context.state('time_unassigned').pack(timeunassigned)

    timeassigned = context.state('time_assigned').unpack(Time)
    report.timeAssigned = timeassigned.time
    context.state('time_assigned').pack(timeassigned)

    timeprogress = context.state('time_in_progress').unpack(Time)
    report.timeInProgress = timeprogress.time
    context.state('time_in_progress').pack(timeprogress)

    timedelivered = context.state('time_delivered').unpack(Time)
    report.timeDelivered = timedelivered.time
    context.state('time_delivered').pack(timedelivered)

    report.test = str(report.timeDelivered - report.timeUnassigned)

    return report
        

def compute_status(order_update:OrderUpdate, state):
    # Compute the status update, after an order has reached a new status
    now = datetime.now()

    if state == 0:
        status = "Order:%s Status:UNASSIGNED Time:%s VehicleId:%s" % (
            order_update.id, now.strftime("%d.%m.%Y - %H:%M:%S"), order_update.vehicle)
    elif state == 1:
        status = "Order:%s Status:ASSIGNED Time:%s VehicleId:%s" % (
            order_update.id, now.strftime("%d.%m.%Y - %H:%M:%S"), order_update.vehicle)
    elif state == 2:
        status = "Order:%s Status:IN_PROGRESS Time:%s VehicleId:%s" % (
            order_update.id, now.strftime("%d.%m.%Y - %H:%M:%S"), order_update.vehicle)
    elif state == 3:
        status = "Order:%s Status:DELIVERED Time:%s VehicleId:%s" % (
            order_update.id, now.strftime("%d.%m.%Y - %H:%M:%S"), order_update.vehicle)
    else:
        status = "Order:%s Status:UNKNOWN Time:%s VehicleId:%s" % (
            order_update.id, now.strftime("%d.%m.%Y - %H:%M:%S"), order_update.vehicle)

    response = OrderStatus()
    response.id = order_update.id
    response.status = status

    return response


handler = RequestReplyHandler(functions)

#
# Serve the endpoint
#

app = Flask(__name__)


@app.route('/statefun', methods=['POST'])
def handle():
    response_data = handler(request.data)
    response = make_response(response_data)
    response.headers.set('Content-Type', 'application/octet-stream')
    return response

if __name__ == "__main__":
    app.run()
