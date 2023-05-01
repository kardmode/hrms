# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cstr, date_diff, getdate,get_time

from frappe.utils.csvutils import UnicodeWriter
from frappe.utils.dateutils import parse_date

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

from hrms.hr.utils import get_holiday_dates_for_employee


class UploadAttendance(Document):
	pass


@frappe.whitelist()
def get_template():
	if not frappe.has_permission("Attendance", "create"):
		raise frappe.PermissionError

	args = frappe.local.form_dict

	if getdate(args.from_date) > getdate(args.to_date):
		frappe.throw(_("To Date should be greater than From Date"))

	w = UnicodeWriter()
	w = add_header(w)

	try:
		w = add_data(w, args)
	except Exception as e:
		frappe.clear_messages()
		frappe.respond_as_web_page("Holiday List Missing", html=e)
		return

	# write out response as a type csv
	frappe.response["result"] = cstr(w.getvalue())
	frappe.response["type"] = "csv"
	frappe.response["doctype"] = "Attendance"

def add_header(w):
	w.writerow(["Employee", "Attendance Date", "Arrival Time", "Departure Time"])


	return w

# def add_header(w):
	# status = ", ".join(
		# (frappe.get_meta("Attendance").get_field("status").options or "").strip().split("\n")
	# )
	# w.writerow(["Notes:"])
	# w.writerow(["Please do not change the template headings"])
	# w.writerow(["Status should be one of these values: " + status])
	# w.writerow(["If you are overwriting existing attendance records, 'ID' column mandatory"])
	# w.writerow(
		# ["ID", "Employee", "Employee Name", "Date", "Status", "Leave Type", "Company", "Naming Series"]
	# )
	# return w


def add_data(w, args):
	data = get_data(args)
	writedata(w, data)
	return w


def get_data(args):
	dates = get_dates(args)
	employees = get_active_employees()
	holidays = get_holidays_for_employees(
		[employee.name for employee in employees], args["from_date"], args["to_date"]
	)
	existing_attendance_records = get_existing_attendance_records(args)
	data = []
	for date in dates:
		for employee in employees:
			if getdate(date) < getdate(employee.date_of_joining):
				continue
			if employee.relieving_date:
				if getdate(date) > getdate(employee.relieving_date):
					continue
			existing_attendance = {}
			if (
				existing_attendance_records
				and tuple([getdate(date), employee.name]) in existing_attendance_records
				and getdate(employee.date_of_joining) <= getdate(date)
				and getdate(employee.relieving_date) >= getdate(date)
			):
				existing_attendance = existing_attendance_records[tuple([getdate(date), employee.name])]

			employee_holiday_list = get_holiday_list_for_employee(employee.name)

			row = [
				existing_attendance and existing_attendance.name or "",
				employee.name,
				employee.employee_name,
				date,
				existing_attendance and existing_attendance.status or "",
				existing_attendance and existing_attendance.leave_type or "",
				employee.company,
				existing_attendance and existing_attendance.naming_series or get_naming_series(),
			]
			if date in holidays[employee_holiday_list]:
				row[4] = "Holiday"
			data.append(row)

	return data


def get_holidays_for_employees(employees, from_date, to_date):
	holidays = {}
	for employee in employees:
		holiday_list = get_holiday_list_for_employee(employee)
		holiday = get_holiday_dates_for_employee(employee, getdate(from_date), getdate(to_date))
		if holiday_list not in holidays:
			holidays[holiday_list] = holiday

	return holidays


def writedata(w, data):
	for row in data:
		w.writerow(row)


def get_dates(args):
	"""get list of dates in between from date and to date"""
	no_of_days = date_diff(add_days(args["to_date"], 1), args["from_date"])
	dates = [add_days(args["from_date"], i) for i in range(0, no_of_days)]
	return dates


def get_active_employees():
	employees = frappe.db.get_all(
		"Employee",
		fields=["name", "employee_name", "date_of_joining", "company", "relieving_date"],
		filters={"docstatus": ["<", 2], "status": "Active"},
	)
	return employees


def get_existing_attendance_records(args):
	attendance = frappe.db.sql(
		"""select name, attendance_date, employee, status, leave_type, naming_series
		from `tabAttendance` where attendance_date between %s and %s and docstatus < 2""",
		(args["from_date"], args["to_date"]),
		as_dict=1,
	)

	existing_attendance = {}
	for att in attendance:
		existing_attendance[tuple([att.attendance_date, att.employee])] = att

	return existing_attendance


def get_naming_series():
	series = frappe.get_meta("Attendance").get_field("naming_series").options.strip().split("\n")
	if not series:
		frappe.throw(_("Please setup numbering series for Attendance via Setup > Numbering Series"))
	return series[0]


@frappe.whitelist()
def upload():
	if not frappe.has_permission("Attendance", "create"):
		raise frappe.PermissionError

	from frappe.utils.csvutils import read_csv_content

	rows = read_csv_content(frappe.local.uploaded_file)
	if not rows:
		frappe.throw(_("Please select a csv file"))
	# frappe.enqueue(import_attendances, rows=rows, now=True if len(rows) < 400 else False)
	import_attendances(rows)

def import_attendances(rows):
	def remove_holidays(rows):
		rows = [row for row in rows if row[4] != "Holiday"]
		return rows
		
	from frappe.modules import scrub
	rows = list(filter(lambda x: x and any(x), rows))
	if not rows:
		msg = [_("Please select a csv file")]
		return {"messages": msg, "error": msg}
	#fixme error when importing certain header
	#columns = [scrub(f) for f in rows[0]]

	columns = ["employee","attendance_date","arrival_time","departure_time"]

	rows = rows[1:]
	ret = []
	error = False
	started = False
	
	import json
	params = json.loads(frappe.form_dict.get("params") or '{}')
	
	if not params.get("import_settings"):
		import_settings = "default"
	else:
		import_settings = params.get("import_settings")
		
	# rows = remove_holidays(rows)

	from frappe.utils.csvutils import check_record, import_doc

	for i, row in enumerate(rows):
		if not row: continue
		started = True
		row_idx = i + 1
		d = frappe._dict(zip(columns, row))

		d["doctype"] = "Attendance"
		
		
		date_error = False
		date_object = d.attendance_date
		
		try:
			parse_date(d.attendance_date)

		except Exception as e:
			date_error = True
			ret.append('Date Error for row (#%d) %s : %s' % (row_idx+1,len(row)>1 and row[1] or "", cstr(e)))
		except ValueError as e:
			date_error = True
			ret.append('Date Error for row (#%d) %s : %s' % (row_idx+1,len(row)>1 and row[1] or "", cstr(e)))
		except:
			date_error = True
			ret.append('Date Error for row (#%d) %s' % (row_idx+1,len(row)>1 and row[1] or ""))
		
			try:
				from datetime import datetime
				date_object = datetime.strptime(date_str, '%d/%m/%Y').date()
			except:
				date_error = True
				ret.append('Date Error for row (#%d) %s' % (row_idx+1,len(row)>1 and row[1] or ""))
		

		if date_error == True:
			if import_settings != "ignore":
				error = True
			continue
			
		d.attendance_date = date_object
		
		formatted_attendance_date = getdate(parse_date(d.attendance_date))
		attendance = frappe.db.sql("""select name,docstatus,attendance_date from `tabAttendance` where employee = %s and attendance_date = %s""",(d.employee, formatted_attendance_date),as_dict=True)		
		company = frappe.db.sql("""select company from `tabEmployee` where employee = %s""",(d.employee),as_dict=True)		

		try:
			d["company"] = company[0].company
			
		except Exception as e:
			error = True
			ret.append('Error for row (#%d) %s. No Company Set For Employee' % (row_idx+1,len(row)>1 and row[1] or ""))	

		if import_settings == "ignore":
		
			frappe.publish_realtime('import_attendance', dict(
						progress=i,
						total=len(rows)
					))
					

			if attendance:
				link = ['<a href="#Form/Attendance/{0}">{0}</a>'.format(str(attendance[0].name))]

				# ret.append('Ignored row (#%d) %s : %s - %s' % (row_idx+1,
					# len(row)>1 and row[1] or "", cstr(d.employee),link))
			else:
				try:
					check_record(d)
					ret.append(import_doc(d, "Attendance", 1, row_idx, submit=False))
					
				except Exception as e:
					# error = True
					ret.append('Error for row (#%d) %s : %s' % (row_idx+1,len(row)>1 and row[1] or "", cstr(e)))
					frappe.errprint(frappe.get_traceback())
				
				
		elif import_settings == "update":
		
			frappe.publish_realtime('import_attendance', dict(
					progress=i,
					total=len(rows)
				))
				
			if attendance:
				d["docstatus"] = attendance[0].docstatus
				d["name"] = attendance[0].name
				
			try:
				check_record(d)
				ret.append(import_doc(d, "Attendance", 1, row_idx, submit=False))
			except Exception as e:
				error = True
				ret.append('Error for row (#%d) %s : %s' % (row_idx+1,len(row)>1 and row[1] or "", cstr(e)))
				# frappe.errprint(frappe.get_traceback())
		else:
			if attendance:
				error = True
				link = ['<a href="#Form/Attendance/{0}">{0}</a>'.format(str(attendance[0].name))]
				ret.append('Error for row (#%d) %s : %s - %s. Attendance Date %s Already Marked or Check Spreadsheet For Duplicates' % (row_idx+1,
					len(row)>1 and row[1] or "", cstr(d.employee),str(d.attendance_date),link))
			else:
			
				frappe.publish_realtime('import_attendance', dict(
					progress=i,
					total=len(rows)
				))
				
				try:
					check_record(d)
					ret.append(import_doc(d, "Attendance", 1, row_idx, submit=False))
				except Exception as e:
					error = True
					ret.append('Error for row (#%d) %s : %s' % (row_idx+1,len(row)>1 and row[1] or "", cstr(e)))
					frappe.errprint(frappe.get_traceback())
	
	if not started:
		error = True
		ret.append('Error reading csv file')

	if error:
		frappe.db.rollback()
	else:
		frappe.db.commit()
		
	frappe.publish_realtime('import_attendance', dict(
		messages=ret,
		error=error
	))
	
@frappe.whitelist()
def update_attendance(start_date,end_date):

	if not start_date or not end_date:
		frappe.throw(_("Please enter both start date and end date"))
		
	attendances = frappe.db.sql("""select name from `tabAttendance` where attendance_date between %s and %s and docstatus < 2""",
		(start_date, end_date), as_dict=1)
	
	summary = ""
			
	
	for att in attendances:
		d = frappe.get_doc("Attendance", att.name)
		
		# if d.arrival_time in ["#--:--","00:00","0:00:00","00:00:0"]:
			# d.arrival_time = "00:00:00"
			
		# if d.departure_time in ["#--:--","00:00","0:00:00","00:00:0"]:
			# d.departure_time = "00:00:00"
			
		# d.departure_time = get_time(d.departure_time).strftime("%H:%M:%S")
		# d.arrival_time = get_time(d.arrival_time).strftime("%H:%M:%S")

		d.save()
		
		new_link = '<a href="#Form/Attendance/{0}">{0} - {1} - {2} - {3}</a><br>'.format(d.name,d.employee,d.employee_name,d.attendance_date)
		summary = summary + new_link
	
	return summary
