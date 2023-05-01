# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from __future__ import unicode_literals
import frappe
from frappe.utils import cstr, cint, flt, getdate,date_diff
from frappe import msgprint, _
from calendar import monthrange
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_month_details

def execute(filters=None):
	if not filters: filters = {}
	data = []
	columns = []
	conditions, filters,year = get_conditions(filters)
	
	company = filters.company
	if not company:
		return columns, data
	
	salary_slips = get_salary_slips(conditions,filters)
	
	if not salary_slips:
		return columns, data
		
	columns, earning_types, ded_types = get_columns(filters,salary_slips)

	month_details = get_month_details(year, filters.month)
	
	no_id = filters.no_id
	no_leave = filters.no_leave
	ss_earning_map = get_ss_earning_map(salary_slips)
	ss_ded_map = get_ss_ded_map(salary_slips)
	
	total_salary = 0
	total_count = 0
	
	import math

	
	for count, ss in enumerate(salary_slips,1):
		row = []
		
		if no_leave and (ss.leave_calculation or ss.gratuity_calculation):
			continue
		
		emp_details = frappe.db.sql("""select mol_id, payroll_agent_id , payroll_agent_code from `tabEmployee` where employee = %(employee)s LIMIT 1""", {"employee": ss.employee}, as_dict=1)	
		
		if filters.get("company") == "Science Lab Inc":
			if emp_details:
				payroll_agent_id = emp_details[0].payroll_agent_id
				
				if no_id and not payroll_agent_id:
					continue

				if str(payroll_agent_id).isdigit():
					payroll_agent_id = str(payroll_agent_id).zfill(16)
				
				total_count += 1
				row += ["EDR"]
				row += [payroll_agent_id]
					
			row += [ss.employee_name]
			row += [count]
			row +=	[month_details.month_start_date]
			row +=	[month_details.month_end_date]
			row +=	[ss.leave_without_pay]


			basic_pay = 0
			variable_pay = 0

			for e in earning_types:
				if "salary" in e.lower():
					basic_pay += flt(ss_earning_map.get(ss.name, {}).get(e))
				elif "benefit" in e.lower():
					basic_pay += flt(ss_earning_map.get(ss.name, {}).get(e))
				
			basic_pay = math.ceil(basic_pay)			
			variable_pay = flt(ss.rounded_total) - flt(basic_pay)
			if variable_pay < 0:
				basic_pay = basic_pay + variable_pay
				variable_pay = 0
				
				
			
			row += [basic_pay]
			row += [variable_pay]
			row += [basic_pay + variable_pay]
			row += [""]			

			total_salary = total_salary + basic_pay + variable_pay	
			
			if not(basic_pay == 0 and variable_pay == 0):
				data.append(row)
		
		else:
		
			if emp_details:
			
				payroll_agent_id = emp_details[0].payroll_agent_id
				
				if no_id and not payroll_agent_id:
					continue
			
				row += ["EDR"]
				row += [str(emp_details[0].mol_id).zfill(14)]
				
				if str(payroll_agent_id).isdigit():
					payroll_agent_id = str(payroll_agent_id).zfill(23)
				
				row += [emp_details[0].payroll_agent_code]
				row += [payroll_agent_id]
					
			row +=	[month_details.month_start_date]
			row +=	[month_details.month_end_date]
			row +=	[month_details.month_days]
			

			basic_pay = 0
			variable_pay = 0

			for e in earning_types:
				if "salary" in e.lower():
					basic_pay += flt(ss_earning_map.get(ss.name, {}).get(e))
				elif "benefit" in e.lower():
					pass
		
				
			basic_pay = math.ceil(basic_pay)			
			variable_pay = flt(ss.rounded_total) - flt(basic_pay)
			if variable_pay < 0:
				basic_pay = basic_pay + variable_pay
				variable_pay = 0
				
				
			variable_pay = 0
			total_salary = total_salary + basic_pay + variable_pay	
			row += [basic_pay]
			row += [variable_pay]
			row +=	[ss.leave_without_pay]
			row += [""]			

			if not(basic_pay == 0  and variable_pay == 0):
				data.append(row)
	
	row = []
	row += ["SCR"]
	
	company_details = []
	if company:
		company_details = frappe.db.sql("""select establishment_id,default_payroll_agent from `tabCompany Licenses` where company = %(company)s LIMIT 1""", {"company": company}, as_dict=1)	

	establishment_id = ""
	default_payroll_agent = ""
	if company_details:
		establishment_id = company_details[0].establishment_id
		default_payroll_agent = company_details[0].default_payroll_agent
		
	import time

	if filters.get("company") == "Science Lab Inc":
		row += [default_payroll_agent]
		row += ["360"]
		
		creation_date = time.strftime("%Y-%m-%d")
		creation_time = time.strftime("%H%M")
		row += [str(filters.month).zfill(2)+str(year)]
		row += [""]
		row += [""]
		row += [""]
		row += [total_count]
		row += [""]
		row += [total_salary]
		row += ["accounts@maarifagroup.com"]
		data.append(row)
		
		creation_date = time.strftime("%Y%m%d")
		creation_time = "{:<06}".format(creation_time)
		row = [default_payroll_agent + "PR" + creation_date + creation_time + ".SIF"]
		row += ["","","","","","","","","",""]
		data.append(row)
	else:
		row += [str(establishment_id).zfill(13)]
		row += [default_payroll_agent]
		
		creation_date = time.strftime("%Y-%m-%d")
		creation_time = time.strftime("%H%M")
		row += [creation_date]
		row += [creation_time]
		row += [str(filters.month).zfill(2)+str(year)]
		row += [len(salary_slips)]
		row += [total_salary]
		row += ["AED"]
		row += [company]
		row += ["accounts@maarifagroup.com"]
		data.append(row)
		
		creation_date = time.strftime("%y%m%d")
		creation_time = "{:<06}".format(creation_time)
		row = [establishment_id + creation_date + creation_time + ".SIF"]
		row += ["","","","","","","","","",""]
		data.append(row)
	
	return columns, data
	
def get_columns(filters,salary_slips):
	
	# 7 columns
	if filters.get("company") == "Science Lab Inc":
		columns = [
			_("Type") + "::75", "Customer No::140","Customer Name::150","Emp Ref No::80","Start Date::80",
		"End Date::80","Days on Leave::50"
		]
	else:
	# 7 columns
		columns = [
			_("Type") + "::75", "MOL ID::140","Agent Code::80","Agent ID::200","Start Date::80",
			"End Date::80","Number of Days::50"
		]
		
	
	salary_components = {_("Earning"): [], _("Deduction"): []}

	for component in frappe.db.sql("""select distinct sd.salary_component, sc.type
		from `tabSalary Detail` sd, `tabSalary Component` sc
		where sc.name=sd.salary_component and sd.amount != 0 and sd.parent in (%s)""" %
		(', '.join(['%s']*len(salary_slips))), tuple([d.name for d in salary_slips]), as_dict=1):
		salary_components[component.type].append(component.salary_component)
	
	# 11 columns
	if filters.get("company") == "Science Lab Inc":
		columns = columns +	["Fixed Salary::100", "Variable Salary::100","Total Amount::100","::100"]
	else:
		# 11 columns
		columns = columns +	["Fixed Salary::100", "Variable Salary::100","Days on Leave::50","::100"]

	
	return columns, salary_components[_("Earning")], salary_components[_("Deduction")]
	
	
	
	

def get_salary_slips(conditions,filters):
	salary_slips = frappe.db.sql("""select name,employee, employee_name, leave_calculation, gratuity_calculation,leave_without_pay,rounded_total from `tabSalary Slip` where docstatus < 2 %s
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
	

	
	return conditions, filters,year
	
def get_ss_earning_map(salary_slips):

	ss_earnings = frappe.db.sql("""select parent, salary_component, amount,default_amount 
		from `tabSalary Detail` where parent in (%s)""" %
		(', '.join(['%s']*len(salary_slips))), tuple([d.name for d in salary_slips]), as_dict=1)

	
	ss_earning_map = {}
	for d in ss_earnings:
		ss_earning_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, [])
		ss_earning_map[d.parent][d.salary_component] = flt(d.amount)
	
	return ss_earning_map

def get_ss_ded_map(salary_slips):
	ss_deductions = frappe.db.sql("""select parent, salary_component, amount,default_amount 
		from `tabSalary Detail` where parent in (%s)""" %
		(', '.join(['%s']*len(salary_slips))), tuple([d.name for d in salary_slips]), as_dict=1)
	
	ss_ded_map = {}
	for d in ss_deductions:
		ss_ded_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, [])
		ss_ded_map[d.parent][d.salary_component] = flt(d.amount)
	
	return ss_ded_map


		
def calculate_lwp(start_date,employee, holidays, working_days):
		lwp = 0
		holidays = "','".join(holidays)
		for d in range(working_days):
			dt = add_days(cstr(getdate(start_date)), d)
			leave = frappe.db.sql("""
				select t1.name, t1.half_day
				from `tabLeave Application` t1, `tabLeave Type` t2
				where t2.name = t1.leave_type
				and t2.is_lwp = 1
				and t1.docstatus < 2
				and t1.status in ('Approved','Back From Leave')
				and t1.employee = %(employee)s
				and CASE WHEN t2.include_holiday != 1 THEN %(dt)s not in ('{0}') and %(dt)s between from_date and to_date
				WHEN t2.include_holiday THEN %(dt)s between from_date and to_date
				END
				""".format(holidays), {"employee": employee, "dt": dt})
			if leave:
				lwp = cint(leave[0][1]) and (lwp + 0.5) or (lwp + 1)
		
		return lwp