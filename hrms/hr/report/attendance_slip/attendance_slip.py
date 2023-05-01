# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import cstr, cint, flt, getdate, rounded
from frappe import msgprint, _
from calendar import monthrange

def execute(filters=None):
	if not filters: filters = {}

	conditions, filters = get_conditions(filters)
	columns = get_columns(filters)
	att_map = get_attendance_map(conditions, filters)
	emp_map = get_emp_details()
	
	reportdate = str(filters.month) + '/'+(filters.fiscal_year)
	data = []
	
	
	for emp_det in emp_map:
		emp = att_map.get(emp_det.name)
		if not emp:
			continue
			
		letter_head = frappe.db.get_value("Company", emp_det.company, "default_letter_head") or ""
		filters["letter_head"] = letter_head

		row = [emp_det.name, emp_det.employee_name, emp_det.designation,filters.letter_head]
		row += [reportdate,'','','','','','']
		data.append(row)
		
		total_nt = 0
		total_ot = 0
		total_otf = 0
		total_oth = 0
		import calendar

		for day in range(filters["total_days_in_month"]):
			details = emp.get(day + 1)
			row = ['', '', '','']

			if details:
				arrival_time = details.arrival_time
				departure_time = details.departure_time

				arrival_time = str(arrival_time)[:-3]
				departure_time = str(departure_time)[:-3]

				normal_time = details.normal_time
				overtime = details.overtime
				overtime_fridays = details.overtime_fridays
				overtime_holidays = details.overtime_holidays
			else:
				arrival_time = "--:--"
				departure_time = "--:--"
				normal_time = 0
				overtime = 0
				overtime_fridays = 0
				overtime_holidays = 0
			
			total_ot = flt(total_ot) + flt(overtime)
			total_otf = flt(total_otf) + flt(overtime_fridays)
			total_oth = flt(total_oth) + flt(overtime_holidays)
			total_nt = flt(total_ot) + flt(total_otf) +flt(total_oth)

			
			
			daynumber = calendar.weekday(cint(filters.fiscal_year),cint(filters.month),cint(day+1))
			dayofweek = str(calendar.day_name[daynumber])[:3]
			textdate = dayofweek + ' ' + str(day+1)
			row += [textdate,arrival_time, departure_time,normal_time,overtime, overtime_fridays, overtime_holidays]
			data.append(row)

		row = ['', '', '','']

		row += ['Total',total_nt,'', '',total_ot, total_otf, total_oth]
		data.append(row)
	return columns, data

def get_columns(filters):
	columns = [
		_("Employee") + ":Link/Employee:80", _("Employee Name") + "::120", _("Designation") + "::80",
		 _("Company") + "::140"
	]
	columns += [_("Date") + "::60"]
	columns += [_("Arrival") + ":Time:60",_("Departure") + ":Time:60"]
	columns += [_("Normal") + ":Float:60",_("Overtime") + ":Float:60", _("Overtime Fridays") + ":Float:60",_("Overtime Holidays") + ":Float:60"]
	return columns

	
def get_attendance_map(conditions, filters):
	attendance_list = frappe.db.sql("""select employee, day(attendance_date) as day_of_month,attendance_date,
		arrival_time,departure_time,normal_time,overtime,overtime_fridays,overtime_holidays,status from tabAttendance where %s order by employee, attendance_date""" %
		conditions, filters, as_dict=1)

	att_map = {}
	for d in attendance_list:
		att_map.setdefault(d.employee, frappe._dict()).setdefault(d.day_of_month, "")
		att_map[d.employee][d.day_of_month] = d
	return att_map

def get_conditions(filters):
	if not (filters.get("month") and filters.get("fiscal_year")):
		msgprint(_("Please select month and year"), raise_exception=1)

	filters["month"] = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
		"Dec"].index(filters.month) + 1

	if not filters.get("fiscal_year"):
		msgprint(_("Please select valid year"), raise_exception=1)
	
	if frappe.db.get_value("Fiscal Year", filters.fiscal_year,"year_start_date"):
		year_start_date, year_end_date = frappe.db.get_value("Fiscal Year", filters.fiscal_year, 
			["year_start_date", "year_end_date"])
	else:
		msgprint(_("Please select a valid year"), raise_exception=1)

	
	if int(filters.month) >= int(year_start_date.strftime("%m")):
		year = year_start_date.strftime("%Y")
	else:
		year = year_end_date.strftime("%Y")
	
	filters["total_days_in_month"] = monthrange(cint(year), filters.month)[1]

	conditions = "month(attendance_date) = %(month)s and year(attendance_date) = %(fiscal_year)s"

	if filters.get("employee"): conditions += " and employee = %(employee)s"
	elif filters.get("company"): conditions += " and company = %(company)s"


	return conditions, filters
def get_emp_details():
	emp_map = frappe.db.sql("""select name, employee_name, designation,
		department, branch, company
		from tabEmployee where docstatus < 2
		and status = 'Active' order by employee_name""", as_dict=1)

	return emp_map

