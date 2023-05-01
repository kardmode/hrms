# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from __future__ import unicode_literals
import frappe
from frappe.utils import cstr, cint, flt, getdate
from frappe import msgprint, _
from calendar import monthrange
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_month_details

def execute(filters=None):
	if not filters: filters = {}
	data = []
	columns = []
	
	company = filters.company
	if not company:
		return columns, data
	
	salary_slips = get_salary_slips(filters)

	
	if not salary_slips:
		return columns, data
	columns, earning_types, ded_types = get_columns(salary_slips)
	
	
	ss_earning_map = get_ss_earning_map(salary_slips)
	ss_ded_map = get_ss_ded_map(salary_slips)
	
	no_id = filters.get("no_id") or False
	no_leave = filters.get("no_leave") or False
	

	
	for ss in salary_slips:
		row = []
		
		if no_leave and (ss.leave_calculation or ss.gratuity_calculation):
			continue
		
		emp_details = frappe.db.sql("""select work_permit_id, emirates_id, mol_id, payroll_agent_id , payroll_agent_code from `tabEmployee` where employee = %(employee)s LIMIT 1""", {"employee": ss.employee}, as_dict=1)	
		
		row += [ss.employee, ss.employee_name]

		if emp_details:
			for d in emp_details:
				row += [d.work_permit_id, d.mol_id,d.emirates_id,d.payroll_agent_code,d.payroll_agent_id]
		
		row += [ss.leave_without_pay]
		basic_pay = 0
		variable_pay = 0

		for e in earning_types:
			if "salary" in e.lower():
				basic_pay += flt(ss_earning_map.get(ss.name, {}).get(e))
			elif "benefit" in e.lower():
				if not filters.get("alternate"):
					basic_pay += flt(ss_earning_map.get(ss.name, {}).get(e))
	
			
		import math
		basic_pay = math.ceil(basic_pay)			
		variable_pay = flt(ss.rounded_total) - flt(basic_pay)
		if variable_pay < 0:
			basic_pay = basic_pay + variable_pay
			variable_pay = 0
		
		total_pay = basic_pay + variable_pay
		row += [basic_pay,variable_pay,total_pay]
		
		if not(basic_pay == 0  and variable_pay == 0):
			data.append(row)
	
	return columns, data
	
def get_columns(salary_slips):
	columns = [
		_("Employee") + ":Link/Employee:100", _("Employee Name") + "::180", 
		_("Work Permit ID") + "::100", _("MOL ID") + "::100", _("Emirates ID") + "::150", 
		_("Agent") + ":Link/MRP Payroll Agent:150", _("Agent Reference ID") + "::150"
	]
	
	salary_components = {_("Earning"): [], _("Deduction"): []}

	for component in frappe.db.sql("""select distinct sd.salary_component, sc.type
		from `tabSalary Detail` sd, `tabSalary Component` sc
		where sc.name=sd.salary_component and sd.amount != 0 and sd.parent in (%s)""" %
		(', '.join(['%s']*len(salary_slips))), tuple([d.name for d in salary_slips]), as_dict=1):
		salary_components[component.type].append(component.salary_component)
	
	columns = columns +	["Leave Without Pay::120"]

	columns = columns +	["Basic Pay:Currency:120", "Variable Pay:Currency:120", "Total Pay:Currency:120"]

	
	
	return columns, salary_components[_("Earning")], salary_components[_("Deduction")]
	
	
	
	

def get_salary_slips(filters):
	conditions, filters = get_conditions(filters)
	salary_slips = frappe.db.sql("""select * from `tabSalary Slip` where docstatus < 2 %s
		order by employee_name""" % conditions, filters, as_dict=1)
	
	return salary_slips
	
def get_conditions(filters):
	conditions = ""
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
	
	month_details = get_month_details(year, filters.month)
	filters["from_date"] = month_details.month_start_date
	filters["to_date"] = month_details.month_end_date

	if filters.get("from_date"): conditions += " and start_date >= %(from_date)s"
	if filters.get("to_date"): conditions += " and end_date <= %(to_date)s"
	
	
	if filters.get("employee"): conditions += " and employee = %(employee)s"
	elif filters.get("company"): conditions += " and company = %(company)s"
	
	return conditions, filters
	
def get_ss_earning_map(salary_slips):

	ss_earnings = frappe.db.sql("""select parent, salary_component, amount 
		from `tabSalary Detail` where parent in (%s)""" %
		(', '.join(['%s']*len(salary_slips))), tuple([d.name for d in salary_slips]), as_dict=1)

	
	ss_earning_map = {}
	for d in ss_earnings:
		ss_earning_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, [])
		ss_earning_map[d.parent][d.salary_component] = flt(d.amount)
	
	return ss_earning_map

def get_ss_ded_map(salary_slips):
	ss_deductions = frappe.db.sql("""select parent, salary_component, amount 
		from `tabSalary Detail` where parent in (%s)""" %
		(', '.join(['%s']*len(salary_slips))), tuple([d.name for d in salary_slips]), as_dict=1)
	
	ss_ded_map = {}
	for d in ss_deductions:
		ss_ded_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, [])
		ss_ded_map[d.parent][d.salary_component] = flt(d.amount)
	
	return ss_ded_map