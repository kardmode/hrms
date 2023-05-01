# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Criterion
from frappe.utils import (
	add_days,
	cint,
	cstr,
	formatdate,
	get_datetime,
	get_link_to_form,
	getdate,
	nowdate,
	get_time,
	time_diff,
	time_diff_in_seconds,
	flt
)

from hrms.hr.doctype.shift_assignment.shift_assignment import has_overlapping_timings
from hrms.hr.utils import get_holiday_dates_for_employee, validate_active_employee


class DuplicateAttendanceError(frappe.ValidationError):
	pass


class OverlappingShiftAttendanceError(frappe.ValidationError):
	pass


class Attendance(Document):
	def validate(self):
		from erpnext.controllers.status_updater import validate_status

		validate_status(self.status, ["Present", "Absent", "On Leave", "Half Day", "Work From Home"])
		validate_active_employee(self.employee)
		self.validate_attendance_date()
		self.validate_duplicate_record()
		self.validate_overlapping_shift_attendance()
		self.validate_employee_status()
		self.check_leave_record()
		self.calculate_total_hours()
		if self.normal_time < 0:
			frappe.throw(_("Working Time cannot be less than 0, date {0}").format(self.attendance_date))


	def on_cancel(self):
		self.unlink_attendance_from_checkins()

	def validate_attendance_date(self):
		date_of_joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")

		new_date = add_days(getdate(nowdate()), 45)


		# leaves can be marked for future dates
		if (
			self.status != "On Leave"
			and not self.leave_application
			and getdate(self.attendance_date) > new_date
		):
			frappe.throw(_("Attendance can not be marked for more than 45 days in the future"))
		elif date_of_joining and getdate(self.attendance_date) < getdate(date_of_joining):
			frappe.throw(_("Attendance date can not be less than employee's joining date"))

	def validate_duplicate_record(self):
		duplicate = get_duplicate_attendance_record(
			self.employee, self.attendance_date, self.shift, self.name
		)

		if duplicate:
			frappe.throw(
				_("Attendance for employee {0} is already marked for the date {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(self.attendance_date),
					get_link_to_form("Attendance", duplicate[0].name),
				),
				title=_("Duplicate Attendance"),
				exc=DuplicateAttendanceError,
			)

	def validate_overlapping_shift_attendance(self):
		attendance = get_overlapping_shift_attendance(
			self.employee, self.attendance_date, self.shift, self.name
		)

		if attendance:
			frappe.throw(
				_("Attendance for employee {0} is already marked for an overlapping shift {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(attendance.shift),
					get_link_to_form("Attendance", attendance.name),
				),
				title=_("Overlapping Shift Attendance"),
				exc=OverlappingShiftAttendanceError,
			)

	def validate_employee_status(self):
		if frappe.db.get_value("Employee", self.employee, "status") == "Inactive":
			frappe.throw(_("Cannot mark attendance for an Inactive employee {0}").format(self.employee))

	def check_leave_record(self):
		leave_record = frappe.db.sql(
			"""
			select leave_type, half_day, half_day_date
			from `tabLeave Application`
			where employee = %s
				and %s between from_date and to_date
				and status = 'Approved'
				and docstatus = 1
		""",
			(self.employee, self.attendance_date),
			as_dict=True,
		)
		if leave_record:
			for d in leave_record:
				self.leave_type = d.leave_type
				if d.half_day_date == getdate(self.attendance_date):
					self.status = "Half Day"
					frappe.msgprint(
						_("Employee {0} on Half day on {1}").format(self.employee, formatdate(self.attendance_date))
					)
				else:
					self.status = "On Leave"
					frappe.msgprint(
						_("Employee {0} is on Leave on {1}").format(self.employee, formatdate(self.attendance_date))
					)

		if self.status in ("On Leave", "Half Day"):
			if not leave_record:
				frappe.msgprint(
					_("No leave record found for employee {0} on {1}").format(
						self.employee, formatdate(self.attendance_date)
					),
					alert=1,
				)
		elif self.leave_type:
			self.leave_type = None
			self.leave_application = None

	def validate_employee(self):
		emp = frappe.db.sql(
			"select name from `tabEmployee` where name = %s and status = 'Active'", self.employee
		)
		if not emp:
			frappe.throw(_("Employee {0} is not active or does not exist").format(self.employee))

	def unlink_attendance_from_checkins(self):
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		linked_logs = (
			frappe.qb.from_(EmployeeCheckin)
			.select(EmployeeCheckin.name)
			.where(EmployeeCheckin.attendance == self.name)
			.for_update()
			.run(as_dict=True)
		)

		if linked_logs:
			(
				frappe.qb.update(EmployeeCheckin)
				.set("attendance", "")
				.where(EmployeeCheckin.attendance == self.name)
			).run()

			frappe.msgprint(
				msg=_("Unlinked Attendance record from Employee Checkins: {}").format(
					", ".join(get_link_to_form("Employee Checkin", log.name) for log in linked_logs)
				),
				title=_("Unlinked logs"),
				indicator="blue",
				is_minimizable=True,
				wide=True,
			)
			
	def calculate_total_hours(self):
	
		if self.arrival_time in ["#--:--","00:00","0:00:00","00:00:0"]:
			self.arrival_time = "00:00:00"
			
		if self.departure_time in ["#--:--","00:00","0:00:00","00:00:0"]:
			self.departure_time = "00:00:00"
		
		try:
			self.departure_time = get_time(self.departure_time ).strftime("%H:%M:%S")
		except Exception as e:
			frappe.throw(_("Possible error in departure time {0} for employee {1}: {2}").format(self.departure_time,self.employee, cstr(e)))
		except ValueError as e:
			frappe.throw(_("Possible error in departure time {0} for employee {1}: {2}").format(self.departure_time,self.employee, cstr(e)))
		except:
			frappe.throw(_("Possible error in departure time {0} for employee {1}: {2}").format(self.departure_time,self.employee))
		
		try:
			self.arrival_time = get_time(self.arrival_time).strftime("%H:%M:%S")
		except Exception as e:
			frappe.throw(_("Possible error in arrival time {0} for employee {1}").format(self.arrival_time,self.employee, cstr(e)))
		except ValueError as e:
			frappe.throw(_("Possible error in arrival time {0} for employee {1}").format(self.arrival_time,self.employee, cstr(e)))
		except:
			frappe.throw(_("Possible error in arrival time {0} for employee {1}").format(self.arrival_time,self.employee))
			
		
		totalworkhours = 0
		try:
			totalworkhours = flt(time_diff_in_seconds(self.departure_time,self.arrival_time))/3600
		except:
			try:
				time = time_diff(self.departure_time,self.arrival_time)
				totalworkhours = flt(time.hour) + flt(time.minute)/60 + flt(time.second)/3600
			except:
				frappe.throw(_("Possible error in arrival time {0} or departure time {1} for employee {2}").format(self.arrival_time,self.departure_time,self.employee))

		
		
		
		if totalworkhours < 0:
			frappe.throw(_("Working time cannot be negative. Please check arrival time {0} or departure time {1} for employee {2} on date {3}").format(self.arrival_time,self.departure_time,self.employee,self.attendance_date))
		elif totalworkhours > 24:
			frappe.throw(_("Working time cannot be greater than 24. Please check arrival time {0} or departure time {1} for employee {2} on date {3}").format(self.arrival_time,self.departure_time,self.employee,self.attendance_date))

		self.working_time = totalworkhours
		
		if not self.department:
			self.department = frappe.db.get_value("Employee", self.employee, "department")
		
		working_hours = frappe.db.sql("""select working_hours from `tabMRP Working Hours`
				where %s >= from_date AND %s <= to_date and (department = %s or department = 'All Departments' or ISNULL(NULLIF(department, '')))""", (self.attendance_date,self.attendance_date,self.department))

		if working_hours:
			self.normal_time = flt(working_hours[0][0])
		else:
			self.normal_time = flt(frappe.db.get_single_value("MRP Regulations", "working_hours"))
		
		weekends = []
		weekend_tb = frappe.get_list('MRP Day Selector', ['day'], 
			filters = {'parent':'MRP Regulations', 'parenttype':'MRP Regulations', 'parentfield' : 'weekends'}, parent_doctype="MRP Regulations")
			
		for d in weekend_tb:
			weekends.append(d.day)
		
		weekday_name = get_datetime(self.attendance_date).strftime('%A')
			
		self.overtime = 0
		self.overtime_fridays = 0
		self.overtime_holidays = 0
		self.mrp_overtime = 0
		self.mrp_overtime_type = "Weekdays"
		
		if self.status not in ["On Leave","Half Day"]:
			self.status = 'Present'
		
		if len(self.get_holidays_for_employee(self.attendance_date,self.attendance_date)):
			self.normal_time = 0
			self.overtime_holidays = flt(totalworkhours) - flt(self.normal_time)
			self.mrp_overtime = flt(totalworkhours) - flt(self.normal_time)
			self.mrp_overtime_type = "Holidays"
		elif weekday_name in weekends:
			self.normal_time = 0
			self.overtime_fridays = flt(totalworkhours) - flt(self.normal_time)
			self.mrp_overtime = flt(totalworkhours) - flt(self.normal_time)
			self.mrp_overtime_type = "Weekends"
		else:		
			if totalworkhours > self.normal_time:
				self.overtime = flt(totalworkhours) - flt(self.normal_time)
				self.mrp_overtime = flt(totalworkhours) - flt(self.normal_time)
				self.mrp_overtime_type = "Weekdays"
				if self.status == "On Leave":
					frappe.throw(_("Employee on leave this day but has attendance. Please check the time for employee {0}, date {1}").format(self.employee,self.attendance_date))

			elif totalworkhours > 2:
				self.normal_time = totalworkhours
				if self.status == "On Leave":
					frappe.throw(_("Employee on leave this day but has attendance. Please check the time for employee {0}, date {1}").format(self.employee,self.attendance_date))

			elif totalworkhours > 0:
				frappe.throw(_("Work Hours under 2. Please check the time for employee {0}, date {1}").format(self.employee,self.attendance_date))
			elif totalworkhours < 0:
				frappe.throw(_("Work Hours negative. Please check the time for employee {0}, date {1}").format(self.employee,self.attendance_date))
			else:
				if self.arrival_time == "00:00:00" and self.departure_time == "00:00:00":
					self.normal_time = 0
					self.working_time = 0
					if self.status != "On Leave":
						self.status = 'Absent'
				else:
					frappe.throw(_("Work Hours equal 0. Please check the time for employee {0}, date {1}, arrival time {2}, departure time {3}").format(self.employee,self.attendance_date,self.arrival_time,self.departure_time))


	def get_holidays_for_employee(self, start_date, end_date):
		holidays = frappe.db.sql("""select t1.holiday_date
			from `tabHoliday` t1, tabEmployee t2
			where t1.parent = t2.holiday_list and t2.name = %s
			and t1.holiday_date between %s and %s""",
			(self.employee, start_date, end_date))
			
		if not holidays:
			holidays = frappe.db.sql("""select t1.holiday_date
				from `tabHoliday` t1, `tabHoliday List` t2
				where t1.parent = t2.name and t2.is_default = 1
				and t1.holiday_date between %s and %s""", 
				(start_date, end_date))
		
		holidays = [cstr(i[0]) for i in holidays]
		return holidays

def get_duplicate_attendance_record(employee, attendance_date, shift, name=None):
	attendance = frappe.qb.DocType("Attendance")
	query = (
		frappe.qb.from_(attendance)
		.select(attendance.name)
		.where((attendance.employee == employee) & (attendance.docstatus < 2))
	)

	if shift:
		query = query.where(
			Criterion.any(
				[
					Criterion.all(
						[
							((attendance.shift.isnull()) | (attendance.shift == "")),
							(attendance.attendance_date == attendance_date),
						]
					),
					Criterion.all(
						[
							((attendance.shift.isnotnull()) | (attendance.shift != "")),
							(attendance.attendance_date == attendance_date),
							(attendance.shift == shift),
						]
					),
				]
			)
		)
	else:
		query = query.where((attendance.attendance_date == attendance_date))

	if name:
		query = query.where(attendance.name != name)

	return query.run(as_dict=True)


def get_overlapping_shift_attendance(employee, attendance_date, shift, name=None):
	if not shift:
		return {}

	attendance = frappe.qb.DocType("Attendance")
	query = (
		frappe.qb.from_(attendance)
		.select(attendance.name, attendance.shift)
		.where(
			(attendance.employee == employee)
			& (attendance.docstatus < 2)
			& (attendance.attendance_date == attendance_date)
			& (attendance.shift != shift)
		)
	)

	if name:
		query = query.where(attendance.name != name)

	overlapping_attendance = query.run(as_dict=True)

	if overlapping_attendance and has_overlapping_timings(shift, overlapping_attendance[0].shift):
		return overlapping_attendance[0]
	return {}


@frappe.whitelist()
def get_events(start, end, filters=None):
	events = []

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user})

	if not employee:
		return events

	from frappe.desk.reportview import get_filters_cond

	conditions = get_filters_cond("Attendance", filters, [])
	add_attendance(events, start, end, conditions=conditions)
	return events


def add_attendance(events, start, end, conditions=None):
	query = """select name, attendance_date, status
		from `tabAttendance` where
		attendance_date between %(from_date)s and %(to_date)s
		and docstatus < 2"""
	if conditions:
		query += conditions

	for d in frappe.db.sql(query, {"from_date": start, "to_date": end}, as_dict=True):
		e = {
			"name": d.name,
			"doctype": "Attendance",
			"start": d.attendance_date,
			"end": d.attendance_date,
			"title": cstr(d.status),
			"docstatus": d.docstatus,
		}
		if e not in events:
			events.append(e)


def mark_attendance(
	employee,
	attendance_date,
	status,
	shift=None,
	leave_type=None,
	ignore_validate=False,
	late_entry=False,
	early_exit=False,
):
	if get_duplicate_attendance_record(employee, attendance_date, shift):
		return

	if get_overlapping_shift_attendance(employee, attendance_date, shift):
		return

	company = frappe.db.get_value("Employee", employee, "company")
	attendance = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": employee,
			"attendance_date": attendance_date,
			"status": status,
			"company": company,
			"shift": shift,
			"leave_type": leave_type,
			"late_entry": late_entry,
			"early_exit": early_exit,
		}
	)
	attendance.flags.ignore_validate = ignore_validate
	attendance.insert()
	attendance.submit()
	return attendance.name


@frappe.whitelist()
def mark_bulk_attendance(data):
	import json

	if isinstance(data, str):
		data = json.loads(data)
	data = frappe._dict(data)
	company = frappe.get_value("Employee", data.employee, "company")
	if not data.unmarked_days:
		frappe.throw(_("Please select a date."))
		return

	for date in data.unmarked_days:
		doc_dict = {
			"doctype": "Attendance",
			"employee": data.employee,
			"attendance_date": get_datetime(date),
			"status": data.status,
			"company": company,
		}
		attendance = frappe.get_doc(doc_dict).insert()
		attendance.submit()


@frappe.whitelist()
def get_unmarked_days(employee, from_date, to_date, exclude_holidays=0):
	joining_date, relieving_date = frappe.get_cached_value(
		"Employee", employee, ["date_of_joining", "relieving_date"]
	)

	from_date = max(getdate(from_date), joining_date or getdate(from_date))
	to_date = min(getdate(to_date), relieving_date or getdate(to_date))

	records = frappe.get_all(
		"Attendance",
		fields=["attendance_date", "employee"],
		filters=[
			["attendance_date", ">=", from_date],
			["attendance_date", "<=", to_date],
			["employee", "=", employee],
			["docstatus", "!=", 2],
		],
	)

	marked_days = [getdate(record.attendance_date) for record in records]

	if cint(exclude_holidays):
		holiday_dates = get_holiday_dates_for_employee(employee, from_date, to_date)
		holidays = [getdate(record) for record in holiday_dates]
		marked_days.extend(holidays)

	unmarked_days = []

	while from_date <= to_date:
		if from_date not in marked_days:
			unmarked_days.append(from_date)

		from_date = add_days(from_date, 1)

	return unmarked_days
