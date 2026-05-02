import json

from datetime import date

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    TemplateView, CreateView, UpdateView, DeleteView, ListView
)

from .forms import RegisterForm, TransactionForm, CategoryForm
from .models import Transaction, Category


# ──────────────────────────────────────────────
#  Authentication Views
# ──────────────────────────────────────────────

class RegisterView(CreateView):
    """Handles new user registration."""
    form_class = RegisterForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        user = form.save()
        # Create default categories for the new user
        default_categories = [
            'Food', 'Travel', 'Bills', 'Entertainment',
            'Shopping', 'Health', 'Education', 'Salary',
            'Freelance', 'Investment', 'Other',
        ]
        for cat_name in default_categories:
            Category.objects.get_or_create(name=cat_name, user=user)
        login(self.request, user)
        messages.success(self.request, f'Welcome, {user.username}! Your account has been created.')
        return redirect(self.success_url)

    def dispatch(self, request, *args, **kwargs):
        # Redirect logged-in users away from register page
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)


# ──────────────────────────────────────────────
#  Dashboard View
# ──────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard showing summaries, charts, and recent transactions."""
    template_name = 'tracker/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # ── Month / Year filter ──
        today = date.today()
        # Accept 'all' for month/year to show all transactions
        sel_month_raw = self.request.GET.get('month', str(today.month))
        sel_year_raw = self.request.GET.get('year', str(today.year))

        if str(sel_month_raw).lower() == 'all':
            selected_month = 'all'
        else:
            try:
                selected_month = int(sel_month_raw)
            except (ValueError, TypeError):
                selected_month = today.month

        if str(sel_year_raw).lower() == 'all':
            selected_year = 'all'
        else:
            try:
                selected_year = int(sel_year_raw)
            except (ValueError, TypeError):
                selected_year = today.year

        # Build filters depending on whether month/year are set to 'all'
        filter_kwargs = {'user': user}
        if selected_month != 'all':
            filter_kwargs['date__month'] = selected_month
        if selected_year != 'all':
            filter_kwargs['date__year'] = selected_year

        transactions = Transaction.objects.filter(**filter_kwargs)

        # ── Aggregate totals ──
        total_income = transactions.filter(type='income').aggregate(
            total=Sum('amount'))['total'] or 0
        total_expense = transactions.filter(type='expense').aggregate(
            total=Sum('amount'))['total'] or 0
        balance = total_income - total_expense

        # ── Chart data: spending by category ──
        expense_by_category = (
            transactions.filter(type='expense')
            .values('category__name')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        chart_labels = [item['category__name'] or 'Uncategorized' for item in expense_by_category]
        chart_data = [float(item['total']) for item in expense_by_category]

        # ── Chart data: income vs expense over days of the month ──
        income_by_day = {}
        expense_by_day = {}
        for txn in transactions:
            day = txn.date.day
            if txn.type == 'income':
                income_by_day[day] = income_by_day.get(day, 0) + float(txn.amount)
            else:
                expense_by_day[day] = expense_by_day.get(day, 0) + float(txn.amount)

        all_days = sorted(set(list(income_by_day.keys()) + list(expense_by_day.keys())))
        line_labels = [str(d) for d in all_days]
        line_income = [income_by_day.get(d, 0) for d in all_days]
        line_expense = [expense_by_day.get(d, 0) for d in all_days]

        # ── Available months for the filter dropdown ──
        months = [
            (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
            (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
            (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
        ]
        years = list(range(today.year - 3, today.year + 2))

        context.update({
            'transactions': transactions[:10],  # Show latest 10
            'total_income': total_income,
            'total_expense': total_expense,
            'balance': balance,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'months': months,
            'years': years,
            # Chart data (serialized to JSON for Chart.js)
            'chart_labels': json.dumps(chart_labels),
            'chart_data': json.dumps(chart_data),
            'line_labels': json.dumps(line_labels),
            'line_income': json.dumps(line_income),
            'line_expense': json.dumps(line_expense),
        })
        return context


# ──────────────────────────────────────────────
#  Transaction CRUD Views
# ──────────────────────────────────────────────

class TransactionListView(LoginRequiredMixin, ListView):
    """List all transactions for the logged-in user."""
    model = Transaction
    template_name = 'tracker/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 15

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


class TransactionCreateView(LoginRequiredMixin, CreateView):
    """Create a new transaction."""
    model = Transaction
    form_class = TransactionForm
    template_name = 'tracker/transaction_form.html'
    success_url = reverse_lazy('dashboard')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, 'Transaction added successfully!')
        return super().form_valid(form)


class TransactionUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an existing transaction (only if owned by the user)."""
    model = Transaction
    form_class = TransactionForm
    template_name = 'tracker/transaction_form.html'
    success_url = reverse_lazy('dashboard')

    def get_queryset(self):
        # Ensure users can only edit their own transactions
        return Transaction.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Transaction updated successfully!')
        return super().form_valid(form)


class TransactionDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a transaction (only if owned by the user)."""
    model = Transaction
    template_name = 'tracker/transaction_confirm_delete.html'
    success_url = reverse_lazy('dashboard')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Transaction deleted successfully!')
        return super().form_valid(form)


# ──────────────────────────────────────────────
#  Category Views
# ──────────────────────────────────────────────

class CategoryListView(LoginRequiredMixin, ListView):
    """List all categories for the logged-in user."""
    model = Category
    template_name = 'tracker/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)


class CategoryCreateView(LoginRequiredMixin, CreateView):
    """Create a new category."""
    model = Category
    form_class = CategoryForm
    template_name = 'tracker/category_form.html'
    success_url = reverse_lazy('category-list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, 'Category created successfully!')
        return super().form_valid(form)


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a category (only if owned by the user)."""
    model = Category
    template_name = 'tracker/category_confirm_delete.html'
    success_url = reverse_lazy('category-list')

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Category deleted successfully!')
        return super().form_valid(form)
