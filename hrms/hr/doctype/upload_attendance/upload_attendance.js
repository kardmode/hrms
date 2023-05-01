// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt



frappe.provide("hrms.hr");

hrms.hr.AttendanceControlPanel = class AttendanceControlPanel extends frappe.ui.form.Controller {
	onload() {
		this.frm.set_value("att_fr_date", frappe.datetime.get_today());
		this.frm.set_value("att_to_date", frappe.datetime.get_today());
		this.frm.set_value("import_settings", "default");
		this.frm.set_value("only_show_errors", 1);
		// this.frm.set_value("start_date", frappe.datetime.get_today());
		// this.frm.set_value("end_date", frappe.datetime.get_today());
		this.set_start_end_dates();
	}

	refresh() {
		this.frm.disable_save();
		this.show_upload();
		this.setup_import_progress();
	}

	get_template() {
		if(!this.frm.doc.att_fr_date || !this.frm.doc.att_to_date) {
			frappe.msgprint(__("Attendance From Date and Attendance To Date is mandatory"));
			return;
		}
		window.location.href = repl(frappe.request.url +
			'?cmd=%(cmd)s&from_date=%(from_date)s&to_date=%(to_date)s', {
				cmd: "hrms.hr.doctype.upload_attendance.upload_attendance.get_template",
				from_date: this.frm.doc.att_fr_date,
				to_date: this.frm.doc.att_to_date,
			});
	}
	
	update_attendance() {
		var me = this;
		frappe.call({
			method: "hrms.hr.doctype.upload_attendance.upload_attendance.update_attendance",
			args: {
				start_date: me.frm.doc.start_date,
				end_date: me.frm.doc.end_date
			},
			freeze: true,
			freeze_message: "Please wait ..",
			callback: function(r) {
				var msg = "";
				if(r.message)
					msg = r.message;
				else
					msg = "0 Attendance Records Updated";
				
				
				cur_frm.set_value("update_log",msg);
				frappe.hide_msgprint();
			}
		});
		
		
	}
	
	start_date(){
		var me = this;
		if(me.frm.doc.start_date){
			me.frm.trigger("set_end_date");
		}
	}

	set_end_date(){
		var me = this;
		frappe.call({
			method: 'hrms.payroll.doctype.payroll_entry.payroll_entry.get_end_date',
			args: {
				frequency: "Monthly",
				start_date: me.frm.doc.start_date
			},
			callback: function (r) {
				if (r.message) {
					me.frm.set_value('end_date', r.message.end_date);
				}
			}
		})
	}
	
	set_start_end_dates() {
		var me = this;
		frappe.call({
				method:'hrms.payroll.doctype.payroll_entry.payroll_entry.get_start_end_dates',
				args:{
					payroll_frequency: "Monthly",
					start_date: frappe.datetime.get_today()
				},
				callback: function(r){
					if (r.message){
						// me.frm.doc.start_date =  r.message.start_date;
						me.frm.set_value('start_date', r.message.start_date);
						// me.frm.refresh_field("start_date");
						me.frm.set_value('end_date', r.message.end_date);
						// me.frm.refresh_field("end_date");
					}
				}
			})
	}

	show_upload() {
		var me = this;
		var $wrapper = $(cur_frm.fields_dict.upload_html.wrapper).empty();
		new frappe.ui.FileUploader({
			wrapper: $wrapper,
			method: 'hrms.hr.doctype.upload_attendance.upload_attendance.upload'
		});

	}

	setup_import_progress() {
		var $log_wrapper = $(this.frm.fields_dict.import_log.wrapper).empty();

		frappe.realtime.on('import_attendance', (data) => {
			if (data.progress) {
				
				// cur_frm.dashboard.show_progress('Import Attendance', data.progress / data.total * 100,
					// __('Importing {0} of {1}', [data.progress, data.total]));
					
				frappe.show_progress('Import Attendance', data.progress,data.total);	
					
				if (data.progress === data.total) {
					// cur_frm.dashboard.hide_progress('Import Attendance');
					frappe.hide_progress('Import Attendance');
				}
			} else if (data.error) {
				this.frm.dashboard.hide();
				frappe.hide_progress('Import Attendance');
				let messages = [`<th>${__('Error in some rows')} `+ data.messages.length +` Records</th>`].concat(data.messages
					.filter(message => message.includes('Error'))
					.map(message => `<tr><td>${message}</td></tr>`))
					.join('');
				$log_wrapper.append('<table class="table table-bordered">' + messages);
			} else if (data.messages) {
				this.frm.dashboard.hide();
				frappe.hide_progress('Import Attendance');
				let messages = [`<th>${__('Import Successful')} `+ data.messages.length +` Records</th>`].concat(data.messages
					.map(message => `<tr><td>${message}</td></tr>`))
					.join('');
				$log_wrapper.append('<table class="table table-bordered">' + messages);
			}
		});
	}
}

cur_frm.cscript = new hrms.hr.AttendanceControlPanel({frm: cur_frm});
