// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

var in_progress = false;

frappe.provide("erpnext.accounts.dimensions");

frappe.ui.form.on('Payroll Entry', {
	onload: function (frm) {
		if (!frm.doc.posting_date) {
			frm.doc.posting_date = frappe.datetime.nowdate();
		}
		frm.toggle_reqd(['payroll_frequency'], !frm.doc.salary_slip_based_on_timesheet);
		
		if (!frm.doc.payroll_frequency) {
			frm.set_value('payroll_frequency','Monthly');
		}
		erpnext.accounts.dimensions.setup_dimension_filters(frm, frm.doctype);
		frm.events.department_filters(frm);
		frm.events.payroll_payable_account_filters(frm);
	},

	department_filters: function (frm) {
		frm.set_query("department", function () {
			return {
				"filters": {
					"company": frm.doc.company,
				}
			};
		});
	},

	payroll_payable_account_filters: function (frm) {
		frm.set_query("payroll_payable_account", function () {
			return {
				filters: {
					"company": frm.doc.company,
					"root_type": "Liability",
					"is_group": 0,
				}
			};
		});
	},

	refresh: function (frm) {
		if (frm.doc.__islocal) {
			frm.trigger("set_start_end_dates");
		}
		if (frm.doc.docstatus == 0 && !frm.doc.__islocal) {
			if (frm.custom_buttons) frm.clear_custom_buttons();
			var slip_status = {'draft':1,'submitted':0};
			// frm.events.add_context_buttons(frm);
			frm.events.add_salary_slip_buttons(frm,slip_status);

		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.page.clear_primary_action();
			frm.add_custom_button(__("Get Employees"),
				function() {
					frm.events.get_employee_details(frm);
				}
			).toggleClass("btn-primary", !(frm.doc.employees || []).length);
		}

		if (
			(frm.doc.employees || []).length
			&& !frappe.model.has_workflow(frm.doctype)
			&& !cint(frm.doc.salary_slips_created)
			&& (frm.doc.docstatus != 2)
		) {
			if (frm.doc.docstatus == 0) {
				frm.page.clear_primary_action();
				frm.page.set_primary_action(__("Create Salary Slips"), () => {
					frm.save("Submit").then(() => {
						frm.page.clear_primary_action();
						frm.refresh();
						frm.events.refresh(frm);
					});
				});
			} else if (frm.doc.docstatus == 1 && frm.doc.status == "Failed") {
				frm.add_custom_button(__("Create Salary Slip"), function () {
					frm.call("create_salary_slips", {}, () => {
						frm.reload_doc();
					});
				}).addClass("btn-primary");
			}
		}

		if (frm.doc.docstatus == 1 && frm.doc.status == "Submitted") {
			if (frm.custom_buttons) frm.clear_custom_buttons();
			frm.events.add_context_buttons(frm);
		}

		if (frm.doc.status == "Failed" && frm.doc.error_message) {
			const issue = `<a id="jump_to_error" style="text-decoration: underline;">issue</a>`;
			let process = (cint(frm.doc.salary_slips_created)) ? "submission" : "creation";

			frm.dashboard.set_headline(
				__("Salary Slip {0} failed. You can resolve the {1} and retry {0}.", [process, issue])
			);

			$("#jump_to_error").on("click", (e) => {
				e.preventDefault();
				frm.scroll_to_field("error_message");
			});
		}

		frappe.realtime.on("completed_salary_slip_creation", function() {
			frm.reload_doc();
		});

		frappe.realtime.on("completed_salary_slip_submission", function() {
			frm.reload_doc();
		});
	},

	get_employee_details: function (frm) {
		return frappe.call({
			doc: frm.doc,
			method: 'fill_employee_details',
		}).then(r => {
			if (r.docs && r.docs[0].employees) {
				frm.employees = r.docs[0].employees;
				frm.dirty();
				frm.save();
				frm.refresh();
				if (r.docs[0].validate_attendance) {
					render_employee_attendance(frm, r.message);
				}
				frm.scroll_to_field("employees");
			}
		});
	},

	create_salary_slips: function(frm) {
		check_saved(frm);
		frappe.confirm(__('This will create Salary Slips. Do you want to proceed?'),
			function() {
				frappe.call({
					method: 'create_salary_slips',
					args: {},
					callback: function(r) {
						frm.refresh();
						frm.toolbar.refresh();
					},
					doc: frm.doc,
					freeze: true,
					freeze_message: 'Creating Salary Slips...'
				});
			},
			function() {
				if(frappe.dom.freeze_count) {
					frappe.dom.unfreeze();
					frm.events.refresh(frm);
				}
			}
		);
	},
	
	// create_salary_slips: function(frm) {
		// frm.call({
			// doc: frm.doc,
			// method: "create_salary_slips",
			// callback: function(r) {
				// frm.refresh();
				// frm.toolbar.refresh();
			// }
		// })
	// },
	
	update_salary_slips: function(frm) {
		
		check_saved(frm);
		frappe.confirm(__('This will update Salary Slips. Do you want to proceed?'),
			function() {

				frappe.call({
					doc: frm.doc,
					method: "update_salary_slips",
					args: {
					},
					callback: function(r) {
						if (r.message)
						{
							if(r.message[0] == 0)
							{
								var msg = "No Salary Slips Updated";
								frappe.msgprint(__(msg)); 
							}
							else
							{
								var msg = r.message[1] + " Entries Updated";
								frappe.msgprint(__(msg)); 
								// cur_frm.cscript.display_activity_log(msg,"Updated");
								// cur_frm.save();
								
							}

						}
							
					},
					freeze: true,
					freeze_message: 'Updating Salary Slips...'
				});
			},
			function() {
				if(frappe.dom.freeze_count) {
					frappe.dom.unfreeze();
					frm.events.refresh(frm);
				}
			}
		);
	},
	
	delete_duplicate_salary_slips: function(frm) {
		
		check_saved(frm);
		frappe.confirm(__('This will delete duplicate Salary Slips. Do you want to proceed?'),
			function() {

				frappe.call({
					doc: frm.doc,
					method: "delete_duplicate_salary_slips",
					args: {
					},
					callback: function(r) {
						if (r.message)
						{
							if(r.message[0] == 0)
							{
								var msg = "No Salary Slips Deleted";
								frappe.msgprint(__(msg)); 
							}
							else
							{
								var msg = r.message[1] + " Entries Deleted";
								frappe.msgprint(__(msg)); 
								// cur_frm.cscript.display_activity_log(msg,"Updated");
								// cur_frm.save();
								
							}

						}
							
					},
					freeze: true,
					freeze_message: 'Deleted Duplicate Salary Slips...'
				});
			},
			function() {
				if(frappe.dom.freeze_count) {
					frappe.dom.unfreeze();
					frm.events.refresh(frm);
				}
			}
		);
	},
	
	
	print_salary_slips: function(frm,format) {
		
		check_saved(frm);
		if(frm.doc.company && frm.doc.start_date && frm.doc.end_date)
		{
			var dialog = new frappe.ui.Dialog({
				title: "Print Salaries",
				fields: [
					{	
						"fieldtype": "Check", 
						"label": __("Don't Include Zero Value Salaries"), 
						"fieldname": "hide_zero_salaries",
						"default":1
					},
					{
						'fieldtype': 'Check',
						'label': __('With Letterhead'),
						'fieldname': 'with_letterhead',
						"default":1
					}
				]
			});
			
			dialog.set_primary_action(__('Print'), args => {
		
				frappe.call({
					doc: frm.doc,
					method: "print_salary_slips",
					args: {
						'hide_zero_salaries': args.hide_zero_salaries
					},
					callback: function(r){
						if (r.message)
						{
							var docname = [];

							r.message.forEach(function (element, index) {
								docname.push(element[0]);
							});
							
							if(docname.length >= 1){
								var json_string = JSON.stringify(docname);
								const with_letterhead = args.with_letterhead ? 1 : 0;
								
								var w = window.open("/api/method/frappe.utils.print_format.download_multi_pdf?"
									+"doctype="+encodeURIComponent("Salary Slip")
									+"&name="+encodeURIComponent(json_string)
									+"&format="+encodeURIComponent(format)
									+'&no_letterhead=' + (with_letterhead ? '0' : '1'));
								if(!w) {
									frappe.msgprint(__("Please enable pop-ups")); return;
								}
							}
						}
						dialog.hide();
					},
					freeze: true,
					freeze_message: 'Printing Salary Slips...'
				});
				
			});
			
			dialog.show();

		} else {
		  frappe.msgprint(__("Company and dates are mandatory"));
		}
	},

	add_context_buttons: function (frm) {
		if (frm.doc.salary_slips_submitted || (frm.doc.__onload && frm.doc.__onload.submitted_ss)) {
			frm.events.add_bank_entry_button(frm);
		} else if (frm.doc.salary_slips_created && frm.doc.status != 'Queued') {
			frm.add_custom_button(__("Submit Salary Slip"), function () {
				submit_salary_slip(frm);
			}).addClass("btn-primary");
		}
	},

	add_bank_entry_button: function (frm) {
		frappe.call({
			method: 'hrms.payroll.doctype.payroll_entry.payroll_entry.payroll_entry_has_bank_entries',
			args: {
				'name': frm.doc.name,
				'payroll_payable_account': frm.doc.payroll_payable_account
			},
			callback: function (r) {
				if (r.message && !r.message.submitted) {
					frm.add_custom_button(__("Make Bank Entry"), function () {
						make_bank_entry(frm);
					}).addClass("btn-primary");
				}
			}
		});
	},

	setup: function (frm) {
		frm.add_fetch('company', 'cost_center', 'cost_center');

		frm.set_query("payment_account", function () {
			var account_types = ["Bank", "Cash"];
			return {
				filters: {
					"account_type": ["in", account_types],
					"is_group": 0,
					"company": frm.doc.company
				}
			};
		});
		frm.set_query("cost_center", function () {
			return {
				filters: {
					"is_group": 0,
					company: frm.doc.company
				}
			};
		}),
		frm.set_query("project", function () {
			return {
				filters: {
					company: frm.doc.company
				}
			};
		});

		frm.set_query('employee', 'employees', () => {
			let error_fields = [];
			let mandatory_fields = ['company', 'payroll_frequency', 'start_date', 'end_date'];

			let message = __('Mandatory fields required in {0}', [__(frm.doc.doctype)]);

			mandatory_fields.forEach(field => {
				if (!frm.doc[field]) {
					error_fields.push(frappe.unscrub(field));
				}
			});

			if (error_fields && error_fields.length) {
				message = message + '<br><br><ul><li>' + error_fields.join('</li><li>') + "</ul>";
				frappe.throw({
					message: message,
					indicator: 'red',
					title: __('Missing Fields')
				});
			}

			return {
				query: "hrms.payroll.doctype.payroll_entry.payroll_entry.employee_query",
				filters: frm.events.get_employee_filters(frm)
			};
		});
	},

	get_employee_filters: function (frm) {
		let filters = {};
		filters['salary_slip_based_on_timesheet'] = frm.doc.salary_slip_based_on_timesheet;

		let fields = ['company', 'start_date', 'end_date', 'payroll_frequency', 'payroll_payable_account',
			'currency', 'department', 'branch', 'designation'];

		fields.forEach(field => {
			if (frm.doc[field]) {
				filters[field] = frm.doc[field];
			}
		});

		if (frm.doc.employees) {
			let employees = frm.doc.employees.filter(d => d.employee).map(d => d.employee);
			if (employees && employees.length) {
				filters['employees'] = employees;
			}
		}
		return filters;
	},

	payroll_frequency: function (frm) {
		frm.trigger("set_start_end_dates").then( ()=> {
			frm.events.clear_employee_table(frm);
		});
	},

	company: function (frm) {
		frm.events.clear_employee_table(frm);
		erpnext.accounts.dimensions.update_dimension(frm, frm.doctype);
		frm.trigger("set_payable_account_and_currency");
	},

	set_payable_account_and_currency: function (frm) {
		frappe.db.get_value("Company", {"name": frm.doc.company}, "default_currency", (r) => {
			frm.set_value('currency', r.default_currency);
		});
		frappe.db.get_value("Company", {"name": frm.doc.company}, "default_payroll_payable_account", (r) => {
			frm.set_value('payroll_payable_account', r.default_payroll_payable_account);
		});
	},

	currency: function (frm) {
		var company_currency;
		if (!frm.doc.company) {
			company_currency = erpnext.get_currency(frappe.defaults.get_default("Company"));
		} else {
			company_currency = erpnext.get_currency(frm.doc.company);
		}
		if (frm.doc.currency) {
			if (company_currency != frm.doc.currency) {
				frappe.call({
					method: "erpnext.setup.utils.get_exchange_rate",
					args: {
						from_currency: frm.doc.currency,
						to_currency: company_currency,
					},
					callback: function (r) {
						frm.set_value("exchange_rate", flt(r.message));
						frm.set_df_property('exchange_rate', 'hidden', 0);
						frm.set_df_property("exchange_rate", "description", "1 " + frm.doc.currency +
							" = [?] " + company_currency);
					}
				});
			} else {
				frm.set_value("exchange_rate", 1.0);
				frm.set_df_property('exchange_rate', 'hidden', 1);
				frm.set_df_property("exchange_rate", "description", "");
			}
		}
	},

	department: function (frm) {
		frm.events.clear_employee_table(frm);
	},

	designation: function (frm) {
		frm.events.clear_employee_table(frm);
	},

	branch: function (frm) {
		frm.events.clear_employee_table(frm);
	},

	start_date: function (frm) {
		if (!in_progress && frm.doc.start_date) {
			frm.trigger("set_end_date");
		} else {
			// reset flag
			in_progress = false;
		}
		frm.events.clear_employee_table(frm);
	},

	project: function (frm) {
		frm.events.clear_employee_table(frm);
	},

	salary_slip_based_on_timesheet: function (frm) {
		frm.toggle_reqd(['payroll_frequency'], !frm.doc.salary_slip_based_on_timesheet);
	},

	set_start_end_dates: function (frm) {
		if (!frm.doc.salary_slip_based_on_timesheet) {
			frappe.call({
				method: 'hrms.payroll.doctype.payroll_entry.payroll_entry.get_start_end_dates',
				args: {
					payroll_frequency: frm.doc.payroll_frequency,
					start_date: frm.doc.posting_date
				},
				callback: function (r) {
					if (r.message) {
						in_progress = true;
						frm.set_value('start_date', r.message.start_date);
						frm.set_value('end_date', r.message.end_date);
					}
				}
			});
		}
	},

	set_end_date: function (frm) {
		frappe.call({
			method: 'hrms.payroll.doctype.payroll_entry.payroll_entry.get_end_date',
			args: {
				frequency: frm.doc.payroll_frequency,
				start_date: frm.doc.start_date
			},
			callback: function (r) {
				if (r.message) {
					frm.set_value('end_date', r.message.end_date);
				}
			}
		});
	},

	validate_attendance: function (frm) {
		if (frm.doc.validate_attendance && frm.doc.employees) {
			frappe.call({
				method: 'validate_employee_attendance',
				args: {},
				callback: function (r) {
					render_employee_attendance(frm, r.message);
				},
				doc: frm.doc,
				freeze: true,
				freeze_message: __('Validating Employee Attendance...')
			});
		} else {
			frm.fields_dict.attendance_detail_html.html("");
		}
	},

	clear_employee_table: function (frm) {
		frm.clear_table('employees');
		frm.refresh();
	},
	add_salary_slip_buttons: function(frm, slip_status) {
		if (!slip_status.draft && !slip_status.submitted) {
			return;
		} else {
			
		}
		
		
		// if (slip_status.draft) {
			// frm.add_custom_button(__("Submit Salary Slips"),
				// function() {
					// submit_salary_slip(frm);
				// }
			// ).addClass("btn-primary");
		// }
		
		
		if (slip_status.draft) {
			frm.add_custom_button(__("Create Salary Slips"),
				function() {
					frm.events.create_salary_slips(frm);
				}
			).addClass("btn-primary");
		}
		
		if (slip_status.draft) {
			frm.add_custom_button(__("Update"),
				function() {
					frm.events.update_salary_slips(frm);
				}, __("Modify Existing Salaries")
			);
			
			frm.add_custom_button(__("Delete Duplicates"),
				function() {
					frm.events.delete_duplicate_salary_slips(frm);
				}, __("Modify Existing Salaries")
			);
		}
	
		
		if (slip_status.draft) {
			frm.add_custom_button(__("Salary Slip and Attendance"),
				function() {
					frm.events.print_salary_slips(frm,"Salary Slip Attendance");
				}, __("Print")
			);
			
			frm.add_custom_button(__("Salary Slip"),
				function() {
					frm.events.print_salary_slips(frm,"Salary Slip");
				}, __("Print")
			);
			
			
			frm.add_custom_button(__("Salary Slips"),
				function() {
					frappe.set_route(
						'List', 'Salary Slip', 
						{	
							"start_date": frm.doc.start_date,
							"company":frm.doc.company,
						}
					);
					
					
				}, __("View")
			);
			
			
			
			
			frm.add_custom_button(__("Attendance Slips"),
				function() {
					frappe.set_route(
						'query-report', 'Attendance Slip', 
						{	
							"month":["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
				"Dec"][frappe.datetime.str_to_obj(frm.doc.start_date).getMonth()],
							"company":frm.doc.company,
						}
					);
				}, __("View")
			);
		}
	},
});

// Submit salary slips

const submit_salary_slip = function (frm) {
	frappe.confirm(__('This will submit Salary Slips and create accrual Journal Entry. Do you want to proceed?'),
		function () {
			frappe.call({
				method: 'submit_salary_slips',
				args: {},
				callback: function () {
					frm.reload_doc();
					frm.events.refresh(frm);
				},
				doc: frm.doc,
				freeze: true,
				freeze_message: __('Submitting Salary Slips and creating Journal Entry...')
			});
		},
		function () {
			if (frappe.dom.freeze_count) {
				frappe.dom.unfreeze();
				frm.events.refresh(frm);
			}
		}
	);
};

let make_bank_entry = function (frm) {
	var doc = frm.doc;
	if (doc.payment_account) {
		return frappe.call({
			doc: cur_frm.doc,
			method: "make_payment_entry",
			callback: function () {
				frappe.set_route(
					'List', 'Journal Entry', {
						"Journal Entry Account.reference_name": frm.doc.name
					}
				);
			},
			freeze: true,
			freeze_message: __("Creating Payment Entries......")
		});
	} else {
		frappe.msgprint(__("Payment Account is mandatory"));
		frm.scroll_to_field('payment_account');
	}
};

let render_employee_attendance = function (frm, data) {
	frm.fields_dict.attendance_detail_html.html(
		frappe.render_template('employees_to_mark_attendance', {
			data: data
		})
	);
};

const check_saved = function (frm) {
	if (frm.is_dirty())
	{
		 frappe.throw(__("Form Needs To Be Saved."));
	}

};

cur_frm.cscript.display_activity_log = function(msg,activity) {
	if(msg) {
		var new_msg = '<p class="padding">'+ frappe.datetime.now_date() +"  " 
			+ frappe.datetime.now_time() + ": " + msg +'</p>';
	
		var final_msg = cur_frm.doc.mrp_activity_log + new_msg;
		cur_frm.set_value("mrp_activity_log",final_msg);
			
	} else {
		// cur_frm.set_value("mrp_activity_log","");
	}
}


/* cur_frm.cscript.display_activity_log = function(msg,activity) {
	var ss_html = $a(cur_frm.fields_dict['activity_log'].wrapper,'div');
	if(msg) {
		ss_html.innerHTML =
			'<div class="padding"><h4>'+ frappe.datetime.now_date() +"  " 
			+ frappe.datetime.now_time() + ": " + activity + '</h4>'+msg+'</div>';
	} else {
		// ss_html.innerHTML = "";
	}
} */
