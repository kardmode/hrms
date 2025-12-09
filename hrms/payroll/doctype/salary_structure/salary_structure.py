# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, cstr, flt

import erpnext


class SalaryStructure(Document):
	def validate(self):
		self.mrp_validate_basic()
		self.set_missing_values()
		self.validate_amount()
		self.strip_condition_and_formula_fields()
		self.validate_max_benefits_with_flexi()
		self.validate_component_based_on_tax_slab()
		self.validate_payment_days_based_dependent_component()
		self.validate_timesheet_component()
		self.validate_formula_setup()
		
	def mrp_validate_basic(self):
		pass
		# if self.is_new():
			# for table in ["earnings"]:
				# for row in self.get(table):
					# if row.salary_component and row.salary_component == "Basic Salary":
						# frappe.msgprint(
							# _("{0} Row #{1}: Do not make a new structure just to change an employee's salary. Make a new assignment with different base value.").format(
								# table.capitalize(),
								# row.idx,
							# ),
							# title=_("Warning"),
							# indicator="orange",
						# )

	def validate_formula_setup(self):
		for table in ["earnings", "deductions"]:
			for row in self.get(table):
				if not row.amount_based_on_formula and row.formula:
					frappe.msgprint(
						_(
							"{0} Row #{1}: Formula is set but {2} is disabled for the Salary Component {3}."
						).format(
							table.capitalize(),
							row.idx,
							frappe.bold(_("Amount Based on Formula")),
							frappe.bold(row.salary_component),
						),
						title=_("Warning"),
						indicator="orange",
					)

	def set_missing_values(self):
		overwritten_fields = [
			"depends_on_payment_days",
			"variable_based_on_taxable_salary",
			"is_tax_applicable",
			"is_flexible_benefit",
		]
		overwritten_fields_if_missing = ["amount_based_on_formula", "formula", "amount"]
		for table in ["earnings", "deductions"]:
			for d in self.get(table):
				component_default_value = frappe.db.get_value(
					"Salary Component",
					cstr(d.salary_component),
					overwritten_fields + overwritten_fields_if_missing,
					as_dict=1,
				)
				if component_default_value:
					for fieldname in overwritten_fields:
						value = component_default_value.get(fieldname)
						if d.get(fieldname) != value:
							d.set(fieldname, value)

					if not (d.get("amount") or d.get("formula")):
						for fieldname in overwritten_fields_if_missing:
							d.set(fieldname, component_default_value.get(fieldname))

	def validate_component_based_on_tax_slab(self):
		for row in self.deductions:
			if row.variable_based_on_taxable_salary and (row.amount or row.formula):
				frappe.throw(
					_(
						"Row #{0}: Cannot set amount or formula for Salary Component {1} with Variable Based On Taxable Salary"
					).format(row.idx, row.salary_component)
				)

	def validate_amount(self):
		if flt(self.net_pay) < 0 and self.salary_slip_based_on_timesheet:
			frappe.throw(_("Net pay cannot be negative"))

	def validate_payment_days_based_dependent_component(self):
		abbreviations = self.get_component_abbreviations()
		for component_type in ("earnings", "deductions"):
			for row in self.get(component_type):
				if (
					row.formula
					and row.depends_on_payment_days
					# check if the formula contains any of the payment days components
					and any(re.search(r"\b" + abbr + r"\b", row.formula) for abbr in abbreviations)
				):
					message = _("Row #{0}: The {1} Component has the options {2} and {3} enabled.").format(
						row.idx,
						frappe.bold(row.salary_component),
						frappe.bold("Amount based on formula"),
						frappe.bold("Depends On Payment Days"),
					)
					message += "<br><br>" + _(
						"Disable {0} for the {1} component, to prevent the amount from being deducted twice, as its formula already uses a payment-days-based component."
					).format(frappe.bold("Depends On Payment Days"), frappe.bold(row.salary_component))
					frappe.throw(message, title=_("Payment Days Dependency"))

	def get_component_abbreviations(self):
		abbr = [d.abbr for d in self.earnings if d.depends_on_payment_days]
		abbr += [d.abbr for d in self.deductions if d.depends_on_payment_days]

		return abbr

	def validate_timesheet_component(self):
		if not self.salary_slip_based_on_timesheet:
			return

		for component in self.earnings:
			if component.salary_component == self.salary_component:
				frappe.msgprint(
					_(
						"Row #{0}: Timesheet amount will overwrite the Earning component amount for the Salary Component {1}"
					).format(self.idx, frappe.bold(self.salary_component)),
					title=_("Warning"),
					indicator="orange",
				)
				break

	def strip_condition_and_formula_fields(self):
		# remove whitespaces from condition and formula fields
		for row in self.earnings:
			row.condition = row.condition.strip() if row.condition else ""
			row.formula = row.formula.strip() if row.formula else ""

		for row in self.deductions:
			row.condition = row.condition.strip() if row.condition else ""
			row.formula = row.formula.strip() if row.formula else ""

	def validate_max_benefits_with_flexi(self):
		have_a_flexi = False
		if self.earnings:
			flexi_amount = 0
			for earning_component in self.earnings:
				if earning_component.is_flexible_benefit == 1:
					have_a_flexi = True
					max_of_component = frappe.db.get_value(
						"Salary Component", earning_component.salary_component, "max_benefit_amount"
					)
					flexi_amount += max_of_component

			if have_a_flexi and flt(self.max_benefits) == 0:
				frappe.throw(_("Max benefits should be greater than zero to dispense benefits"))
			if have_a_flexi and flexi_amount and flt(self.max_benefits) > flexi_amount:
				frappe.throw(
					_(
						"Total flexible benefit component amount {0} should not be less than max benefits {1}"
					).format(flexi_amount, self.max_benefits)
				)
		if not have_a_flexi and flt(self.max_benefits) > 0:
			frappe.throw(
				_("Salary Structure should have flexible benefit component(s) to dispense benefit amount")
			)

	def get_employees(self, **kwargs):
		conditions, values = [], []
		for field, value in kwargs.items():
			if value:
				conditions.append(f"{field}=%s")
				values.append(value)

		condition_str = " and " + " and ".join(conditions) if conditions else ""

		# nosemgrep: frappe-semgrep-rules.rules.frappe-using-db-sql
		employees = frappe.db.sql_list(
			f"select name from tabEmployee where status='Active' {condition_str}",
			tuple(values),
		)

		return employees

	@frappe.whitelist()
	def assign_salary_structure(
		self,
		grade=None,
		department=None,
		designation=None,
		employee=None,
		payroll_payable_account=None,
		from_date=None,
		base=None,
		variable=None,
		income_tax_slab=None,
		fixed_benefits=None,
		variable_benefits=None,
	):
		employees = self.get_employees(
			company=self.company, grade=grade, department=department, designation=designation, name=employee
		)

		if employees:
			if len(employees) > 20:
				frappe.enqueue(
					assign_salary_structure_for_employees,
					timeout=600,
					employees=employees,
					salary_structure=self,
					payroll_payable_account=payroll_payable_account,
					from_date=from_date,
					base=base,
					variable=variable,
					income_tax_slab=income_tax_slab,
					fixed_benefits=fixed_benefits,
					variable_benefits=variable_benefits,
				)
			else:
				assign_salary_structure_for_employees(
					employees,
					self,
					payroll_payable_account=payroll_payable_account,
					from_date=from_date,
					base=base,
					variable=variable,
					income_tax_slab=income_tax_slab,
					fixed_benefits=fixed_benefits,
					variable_benefits=variable_benefits,
				)
		else:
			frappe.msgprint(_("No Employee Found"))


def assign_salary_structure_for_employees(
	employees,
	salary_structure,
	payroll_payable_account=None,
	from_date=None,
	base=None,
	variable=None,
	income_tax_slab=None,
	fixed_benefits=None,
	variable_benefits=None,
):
	salary_structures_assignments = []
	existing_assignments_for = get_existing_assignments(employees, salary_structure, from_date)
	count = 0
	for employee in employees:
		if employee in existing_assignments_for:
			continue
		count += 1

		salary_structures_assignment = create_salary_structures_assignment(
			employee, salary_structure, payroll_payable_account, from_date, base, variable, income_tax_slab, fixed_benefits, variable_benefits
		)
		salary_structures_assignments.append(salary_structures_assignment)
		frappe.publish_progress(
			count * 100 / len(set(employees) - set(existing_assignments_for)),
			title=_("Assigning Structures..."),
		)

	if salary_structures_assignments:
		frappe.msgprint(_("Structures have been assigned successfully"))


def create_salary_structures_assignment(
	employee,
	salary_structure,
	payroll_payable_account,
	from_date,
	base,
	variable,
	income_tax_slab=None,
	fixed_benefits=None,
	variable_benefits=None,
):
	if not payroll_payable_account:
		payroll_payable_account = frappe.db.get_value(
			"Company", salary_structure.company, "default_payroll_payable_account"
		)
		if not payroll_payable_account:
			frappe.throw(_('Please set "Default Payroll Payable Account" in Company Defaults'))
	payroll_payable_account_currency = frappe.db.get_value(
		"Account", payroll_payable_account, "account_currency"
	)
	company_curency = erpnext.get_company_currency(salary_structure.company)
	if (
		payroll_payable_account_currency != salary_structure.currency
		and payroll_payable_account_currency != company_curency
	):
		frappe.throw(
			_("Invalid Payroll Payable Account. The account currency must be {0} or {1}").format(
				salary_structure.currency, company_curency
			)
		)

	assignment = frappe.new_doc("Salary Structure Assignment")
	assignment.employee = employee
	assignment.salary_structure = salary_structure.name
	assignment.company = salary_structure.company
	assignment.currency = salary_structure.currency
	assignment.payroll_payable_account = payroll_payable_account
	assignment.from_date = from_date
	assignment.base = base
	assignment.variable = variable
	
	# Set custom fields to your known values
	if hasattr(assignment, "custom_fixed_benefits"):
		assignment.custom_fixed_benefits = fixed_benefits

	if hasattr(assignment, "custom_variable_benefits"):
		assignment.custom_variable_benefits = variable_benefits
	
	assignment.income_tax_slab = income_tax_slab
	assignment.save(ignore_permissions=True)
	assignment.submit()
	return assignment.name


def get_existing_assignments(employees, salary_structure, from_date):
	# nosemgrep: frappe-semgrep-rules.rules.frappe-using-db-sql
	salary_structures_assignments = frappe.db.sql_list(
		f"""
		SELECT DISTINCT employee FROM `tabSalary Structure Assignment`
		WHERE salary_structure=%s AND employee IN ({", ".join(["%s"] * len(employees))})
		AND from_date=%s AND company=%s AND docstatus=1
		""",
		[salary_structure.name, *employees, from_date, salary_structure.company],
	)
	if salary_structures_assignments:
		frappe.msgprint(
			_(
				"Skipping Salary Structure Assignment for the following employees, as Salary Structure Assignment records already exists against them. {0}"
			).format("\n".join(salary_structures_assignments))
		)
	return salary_structures_assignments


@frappe.whitelist()
def make_salary_slip(
	source_name,
	target_doc=None,
	employee=None,
	posting_date=None,
	as_print=False,
	print_format=None,
	for_preview=0,
	ignore_permissions=False,
):
	def postprocess(source, target):
		if employee:
			employee_details = frappe.db.get_value(
				"Employee", employee, ["employee_name", "branch", "designation", "department"], as_dict=1
			)
			target.employee = employee
			target.employee_name = employee_details.employee_name
			target.branch = employee_details.branch
			target.designation = employee_details.designation
			target.department = employee_details.department

			if posting_date:
				target.posting_date = posting_date

		target.run_method("process_salary_structure", for_preview=for_preview)

	doc = get_mapped_doc(
		"Salary Structure",
		source_name,
		{
			"Salary Structure": {
				"doctype": "Salary Slip",
				"field_map": {
					"total_earning": "gross_pay",
					"name": "salary_structure",
					"currency": "currency",
				},
			}
		},
		target_doc,
		postprocess,
		ignore_child_tables=True,
		ignore_permissions=ignore_permissions,
	)

	if cint(as_print):
		doc.name = f"Preview for {employee}"
		return frappe.get_print(doc.doctype, doc.name, doc=doc, print_format=print_format)
	else:
		return doc


@frappe.whitelist()
def get_employees(salary_structure):
	employees = frappe.get_list(
		"Salary Structure Assignment",
		filters={"salary_structure": salary_structure, "docstatus": 1},
		fields=["employee"],
	)

	if not employees:
		frappe.throw(
			_(
				"There's no Employee with Salary Structure: {0}. Assign {1} to an Employee to preview Salary Slip"
			).format(salary_structure, salary_structure)
		)

	return list(set([d.employee for d in employees]))


@frappe.whitelist()
def get_salary_component(doctype, txt, searchfield, start, page_len, filters):
	sc = frappe.qb.DocType("Salary Component")
	sca = frappe.qb.DocType("Salary Component Account")

	salary_components = (
		frappe.qb.from_(sc)
		.left_join(sca)
		.on(sca.parent == sc.name)
		.select(sc.name, sca.account, sca.company)
		.where(
			(sc.type == filters.get("component_type"))
			& (sc.disabled == 0)
			& (sc[searchfield].like(f"%{txt}%") | sc.name.like(f"%{txt}%"))
		)
		.limit(page_len)
		.offset(start)
	).run(as_dict=True)

	accounts = []
	for component in salary_components:
		if not component.company:
			accounts.append((component.name, component.account, component.company))
		else:
			if component.company == filters["company"]:
				accounts.append((component.name, component.account, component.company))

	return accounts
	
@frappe.whitelist()
def mrp_update_inactive():
	"""
	Deactivate Salary Structures with no active assignments.
	"""
	to_deactivate = []

	# Get all active Salary Structures
	structures = frappe.get_all(
		"Salary Structure",
		filters={"is_active": "Yes", "docstatus": 1},
		fields=["name"]
	)

	for struct in structures:
		assignments = frappe.get_all(
			"Salary Structure Assignment",
			filters={"salary_structure": struct.name, "docstatus": 1},
			fields=["employee"]
		)

		if not assignments:
			to_deactivate.append({"name": struct.name, "reason": "No assignments"})
			continue

		# Check employee status
		active_assignments = 0
		for a in assignments:
			employee_status = frappe.get_value("Employee", a.employee, "status")
			if employee_status != "Left":
				active_assignments += 1

		if active_assignments == 0:
			to_deactivate.append({"name": struct.name, "reason": "All assigned employees left"})

	# Update all deactivated structures in one pass
	for s in to_deactivate:
		frappe.db.set_value("Salary Structure", s["name"], "is_active", "No")

	frappe.db.commit()

	# Build debug message
	if not to_deactivate:
		return "No Salary Structures to deactivate."

	debug_lines = [f"{s['name']}: {s['reason']}" for s in to_deactivate]
	debug_msg = "\n".join(debug_lines)

	return f"Deactivated {len(to_deactivate)} Salary Structures:\n{debug_msg}"

@frappe.whitelist()
def mrp_update_base():
	components = {
		"Basic Salary":{
			"amount_based_on_formula":1,
			"is_tax_applicable": 1,
			"formula":"base"
		},
		# "Overtime Weekdays": {
			# "is_tax_applicable": 1,
			# "formula": "(base * overtime_weekdays_rate * overtime_hours_weekdays) / (standard_days * salary_hours_calculation)"
		# },
		# "Overtime Weekends": {
			# "is_tax_applicable": 1,
			# "formula": "(base * overtime_fridays_rate * overtime_hours_fridays) / (standard_days * salary_hours_calculation)"
		# },
		# "Overtime Holidays": {
			# "is_tax_applicable": 1,
			# "formula": "(base * overtime_holidays_rate * overtime_hours_holidays) / (standard_days * salary_hours_calculation)"
		# },
	}
	
	salary_details = frappe.get_all(
		"Salary Detail",
		filters={
			"parenttype": "Salary Structure",
			"salary_component": ["in", list(components.keys())],
			# "amount_based_on_formula":0,
			# "formula":"",
		},
		fields=["name", "salary_component", "parent","amount_based_on_formula","formula"]
	)
	
	updated = []
	for detail in salary_details:
		comp = detail.salary_component
		props = components.get(comp, {})

		update_fields = props.copy()

		updated.append({
			"name": detail.name,
			"parent": detail.parent,
			"salary_component": comp,
			"original": detail,
			"update_fields": update_fields
		})

		frappe.db.set_value("Salary Detail", detail.name, update_fields)

	# Debug summary
	if not updated:
		return "Debug: No rows found."

	summary = [
		f"{d['parent']} → {d['salary_component']} | original {d['original']} | updates: {d['update_fields']}" 
		for d in updated
	]
	return f"Debug: {len(updated)} Salary Details updated:\n\n" + "\n\n".join(summary)
	
@frappe.whitelist()
def mrp_update_overtime():
	components = {
		"Overtime Weekdays": {
			"is_tax_applicable": 1,
			"formula": "(base * overtime_weekdays_rate * overtime_hours_weekdays) / (standard_days * salary_hours_calculation)"
		},
		"Overtime Weekends": {
			"is_tax_applicable": 1,
			"formula": "(base * overtime_fridays_rate * overtime_hours_fridays) / (standard_days * salary_hours_calculation)"
		},
		"Overtime Holidays": {
			"is_tax_applicable": 1,
			"formula": "(base * overtime_holidays_rate * overtime_hours_holidays) / (standard_days * salary_hours_calculation)"
		},
	}
	
	salary_details = frappe.get_all(
		"Salary Detail",
		filters={
			"parenttype": "Salary Structure",
			"salary_component": ["in", list(components.keys())]
		},
		fields=["name", "salary_component", "parent"]
	)
	
	updated = []
	for detail in salary_details:
		comp = detail.salary_component
		props = components.get(comp, {})

		update_fields = props.copy()

		updated.append({
			"name": detail.name,
			"parent": detail.parent,
			"salary_component": comp,
			"original": detail,
			"update_fields": update_fields
		})

		frappe.db.set_value("Salary Detail", detail.name, update_fields)

	# Debug summary
	if not updated:
		return "Debug: No rows found."

	summary = [
		f"{d['parent']} → {d['salary_component']} | original {d['original']} | updates: {d['update_fields']}" 
		for d in updated
	]
	return f"Debug: {len(updated)} Salary Details updated:\n\n" + "\n\n".join(summary)